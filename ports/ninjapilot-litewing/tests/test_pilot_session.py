"""Exercise firmware admission through encoded frames and real SDK crypto."""
import ctypes as C
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1] / "ai_assistant/src"))
from lrrk_litewing_ai.pilot_admission import PilotAdmission
from lrrk_litewing_ai.pilot_keys import derive_keys
from lrrk_litewing_ai.pilot_wire import Envelope, encode, decode
from test_pilot_crypto_vectors import PIN

RNG = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p, C.c_size_t)

class Candidate(C.Structure):
    _fields_ = [("channels", C.c_uint16 * 8), ("origin_us", C.c_int64), ("sequence", C.c_uint64)]


class FirmwareAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("LRRK_TEST_MBEDTLS_ROOT")
        if not path:
            raise unittest.SkipTest("pinned mbedTLS checkout not supplied")
        source = Path(path)
        if subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() != PIN:
            raise AssertionError("wrong mbedTLS revision")
        if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], text=True):
            raise AssertionError("dirty mbedTLS checkout")
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        out = Path(cls.temp.name)
        (out / "config.h").write_text("#define MBEDTLS_MD_C\n#define MBEDTLS_SHA256_C\n#define MBEDTLS_HKDF_C\n")
        (out / "access.c").write_text(
            '#include "litewing_pilot_session.h"\n'
            'size_t state_size(void) {return sizeof(struct lw_pilot_session);}\n'
            'int phase(struct lw_pilot_session *s) {return s->phase;}\n'
            'void exhaust_sequence(struct lw_pilot_session *s) {s->board_sequence=UINT64_MAX;}\n'
            'int retired_keys(struct lw_pilot_session *s) {\n'
            'const unsigned char *p=(const unsigned char *)&s->keys;\n'
            'for(size_t i=0;i<sizeof(s->keys);++i) if(p[i]) return 0;\n'
            'for(size_t i=0;i<16;++i) if(s->session[i] || s->challenge[i]) return 0;\n'
            'return 1;}\n')
        command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                   '-DMBEDTLS_CONFIG_FILE="config.h"', "-I", str(out),
                   "-I", str(source / "include"), "-I", str(ROOT / "target/include")]
        command += [str(source / "library" / name) for name in ("md.c", "sha256.c", "hkdf.c", "platform_util.c")]
        command += [str(ROOT / "target" / name) for name in
                    ("litewing_pilot_session.c", "litewing_pilot_wire.c", "pios_litewing_pilot_mac.c", "pios_litewing_pilot_keys.c")]
        command += [str(out / "access.c"), "-o", str(out / "session.so")]
        cls.compile_command = command
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(out / "session.so"))
        cls.lib.state_size.restype = C.c_size_t
        cls.lib.phase.argtypes = [C.c_void_p]
        cls.lib.retired_keys.argtypes = [C.c_void_p]
        cls.lib.exhaust_sequence.argtypes = [C.c_void_p]
        cls.lib.lw_session_init.argtypes = [C.c_void_p]
        cls.lib.lw_session_tick.argtypes = [C.c_void_p, C.c_int64]
        cls.lib.lw_session_prepare_control.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t, C.c_int64]
        cls.lib.lw_session_commit_control.argtypes = [C.c_void_p, C.c_int64, C.c_int, C.POINTER(Candidate)]
        cls.lib.lw_session_issue_challenge.argtypes = [C.c_void_p, C.c_void_p,
            C.c_int64, RNG, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
        cls.lib.lw_session_receive.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t,
            C.c_void_p, C.c_int64, C.c_int, C.c_int, RNG, C.c_void_p,
            C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]

    def setUp(self):
        self.state = C.create_string_buffer(self.lib.state_size())
        self.lib.lw_session_init(self.state)
        self.root, self.host = b"r" * 32, b"h" * 32
        self.rng_calls = 0
        self.fail_rng = False
        self.fail_rng_at = 0
        def random(_ctx, dest, size):
            self.rng_calls += 1
            C.memset(dest, self.rng_calls, size)
            return -1 if self.fail_rng or self.rng_calls == self.fail_rng_at else 0
        self.random = RNG(random)

    def receive(self, wire, now, disarmed=1, owner_free=1, capacity=594):
        reply = C.create_string_buffer(b"x" * 594, 594)
        written = C.c_size_t(99)
        rc = self.lib.lw_session_receive(self.state, wire, len(wire), self.root, now,
            disarmed, owner_free, self.random, None, reply, capacity, C.byref(written))
        if rc != 1:
            self.assertEqual(written.value, 0)
        return rc, reply.raw[:written.value]

    def start(self):
        client = PilotAdmission(self.root, self.host)
        rc, challenge = self.receive(client.begin(100), 100)
        self.assertEqual(rc, 1)
        self.assertEqual(self.lib.phase(self.state), 1)
        return client, challenge

    def issue(self, now, capacity=594):
        reply = C.create_string_buffer(594)
        written = C.c_size_t(99)
        rc = self.lib.lw_session_issue_challenge(self.state, self.root, now,
            self.random, None, reply, capacity, C.byref(written))
        if rc != 1:
            self.assertEqual(written.value, 0)
        return rc, reply.raw[:written.value]

    def active(self):
        client, challenge = self.start()
        frame = decode(challenge, self.root, 1)
        keys = derive_keys(self.root, self.host, frame.payload[32:], frame.session)
        self.assertEqual(self.receive(client.receive_challenge(challenge, 200), 300)[0], 1)
        return frame, keys

    def control_wire(self, frame, keys, sequence=2, kind=5, payload=None):
        if payload is None:
            payload = b"\x05\xdc" * 8 if kind == 5 else b""
        return encode(Envelope(0, kind, frame.session, sequence, frame.challenge, payload), keys.c2b)

    def prepare(self, wire, now):
        return self.lib.lw_session_prepare_control(self.state, wire, len(wire), now)

    def commit(self, now, owner_valid=1):
        out = Candidate()
        C.memset(C.byref(out), 0xa5, C.sizeof(out))
        rc = self.lib.lw_session_commit_control(self.state, now, owner_valid, C.byref(out))
        if rc != 3:
            self.assertEqual(bytes(out), bytes(C.sizeof(out)))
        return rc, out

    def test_control_commit_preserves_origin_and_rejects_replay(self):
        frame, keys = self.active()
        wire = self.control_wire(frame, keys)
        self.assertEqual(self.prepare(wire, 500), 3)
        rc, candidate = self.commit(600)
        self.assertEqual(rc, 3)
        self.assertEqual(list(candidate.channels), [1500]*8)
        self.assertEqual((candidate.origin_us, candidate.sequence), (100, 2))
        self.assertEqual(self.prepare(wire, 700), 0)
        self.assertEqual(self.commit(800)[0], 0)
        self.assertEqual(self.prepare(self.control_wire(frame, keys, 3), 900), 3)
        self.assertEqual(self.commit(1000)[1].origin_us, 100)
        self.assertEqual(self.lib.lw_session_tick(self.state, 100100), -1)

    def test_commit_delay_and_lost_ownership_retire_without_candidate(self):
        for now, owner in ((75101, 1), (600, 0), (499, 1)):
            self.lib.lw_session_init(self.state)
            frame, keys = self.active()
            self.assertEqual(self.prepare(self.control_wire(frame, keys), 500), 3)
            self.assertEqual(self.commit(now, owner)[0], 2)
            self.assertEqual(self.lib.phase(self.state), 0)
            self.assertEqual(self.lib.retired_keys(self.state), 1)

    def test_stop_invalidates_prepared_control(self):
        frame, keys = self.active()
        self.assertEqual(self.prepare(self.control_wire(frame, keys), 500), 3)
        self.assertEqual(self.prepare(self.control_wire(frame, keys, 3, kind=6), 600), 2)
        self.assertEqual(self.commit(700)[0], 0)
        self.assertEqual(self.lib.phase(self.state), 0)

    def test_control_payload_sequence_and_authentication_bounds(self):
        frame, keys = self.active()
        for wire in (self.control_wire(frame, keys, 1),
                     self.control_wire(frame, keys, payload=b"x"*15),
                     self.control_wire(frame, keys, payload=b"\x03\xe7"*8),
                     self.control_wire(frame, keys, payload=b"\x07\xd1"*8),
                     self.control_wire(frame, keys, kind=6, payload=b"x")):
            self.assertEqual(self.prepare(wire, 500), 0)
        wire = self.control_wire(frame, keys)
        self.assertEqual(self.prepare(wire[:-1] + bytes([wire[-1]^1]), 500), 0)
        self.assertEqual(self.prepare(wire, 75101), 0)
        self.assertEqual(self.lib.phase(self.state), 2)

    def test_control_origin_cannot_regress_and_only_one_candidate_can_wait(self):
        original, keys = self.active()
        rc, challenge = self.issue(20100)
        self.assertEqual(rc, 1)
        fresh = decode(challenge, keys.b2c, 1)
        self.assertEqual(self.prepare(self.control_wire(fresh, keys), 20200), 3)
        self.assertEqual(self.prepare(self.control_wire(fresh, keys, 3), 20300), 0)
        self.assertEqual(self.commit(20400)[1].origin_us, 20100)
        self.assertEqual(self.prepare(self.control_wire(original, keys, 3), 20500), 0)
        self.assertEqual(self.prepare(self.control_wire(fresh, keys, 3), 20600), 3)
        self.assertEqual(self.commit(20700)[1].sequence, 3)

    def test_exact_control_age_and_sequence_exhaustion(self):
        frame, keys = self.active()
        self.assertEqual(self.prepare(self.control_wire(frame, keys), 75100), 3)
        self.assertEqual(self.commit(75100)[0], 3)
        self.assertEqual(self.prepare(self.control_wire(frame, keys, 2**64-1), 75100), 2)
        self.assertEqual(self.lib.retired_keys(self.state), 1)

    def test_old_session_control_cannot_cross_readmission(self):
        original, keys = self.active()
        old = self.control_wire(original, keys)
        self.assertEqual(self.prepare(self.control_wire(original, keys, kind=6), 500), 2)
        self.active()  # Deterministic fixture RNG advances to distinct session/nonces.
        self.assertEqual(self.prepare(old, 600), 0)
        self.assertEqual(self.commit(700)[0], 0)

    def test_real_host_and_board_mutual_admission(self):
        client, challenge = self.start()
        claim = client.receive_challenge(challenge, 200)
        rc, accept = self.receive(claim, 300)
        self.assertEqual(rc, 1)
        self.assertEqual(self.lib.phase(self.state), 2)
        client.receive_accept(accept, 400)
        self.assertTrue(client.established)
        self.assertEqual(self.receive(claim, 500)[0], 0)
        self.assertEqual(self.lib.lw_session_tick(self.state, 100100), -1)
        self.assertEqual(self.lib.phase(self.state), 0)

    def test_bad_mac_and_owner_conditions_do_not_admit(self):
        hello = PilotAdmission(self.root, self.host).begin(100)
        for wire, disarmed, free in ((hello[:-1] + bytes([hello[-1]^1]), 1, 1),
                                     (hello, 0, 1), (hello, 1, 0)):
            self.assertEqual(self.receive(wire, 100, disarmed, free)[0], 0)
            self.assertEqual(self.lib.phase(self.state), 0)
        client, challenge = self.start()
        claim = client.receive_challenge(challenge, 200)
        self.assertEqual(self.receive(claim, 300, disarmed=0)[0], 0)
        self.assertEqual(self.lib.phase(self.state), 1)

    def test_expired_claim_pending_replacement_and_rollback(self):
        client, challenge = self.start()
        claim = client.receive_challenge(challenge, 200)
        another = PilotAdmission(self.root, b"x"*32).begin(200)
        self.assertEqual(self.receive(another, 200)[0], 0)
        self.assertEqual(self.receive(claim, 75101)[0], 0)
        self.assertEqual(self.lib.lw_session_tick(self.state, 75100), -1)
        self.assertEqual(self.lib.phase(self.state), 0)

    def test_rng_failure_and_small_reply_retire_partial_admission(self):
        hello = PilotAdmission(self.root, self.host).begin(100)
        self.fail_rng = True
        self.assertEqual(self.receive(hello, 100)[0], 2)
        self.assertEqual(self.lib.phase(self.state), 0)
        self.fail_rng = False
        self.assertEqual(self.receive(hello, 200, capacity=1)[0], 2)
        self.assertEqual(self.lib.phase(self.state), 0)

    def test_claim_exact_age_boundary_and_pending_deadline(self):
        client, challenge = self.start()
        claim = client.receive_challenge(challenge, 200)
        self.assertEqual(self.receive(claim, 75100)[0], 1)
        self.assertEqual(self.lib.lw_session_tick(self.state, 100099), 0)
        self.assertEqual(self.lib.lw_session_tick(self.state, 100100), -1)
        self.lib.lw_session_init(self.state)
        self.start()
        self.assertEqual(self.lib.lw_session_tick(self.state, 1000099), 0)
        self.assertEqual(self.lib.lw_session_tick(self.state, 1000100), -1)

    def test_claim_field_binding_and_reflection(self):
        client, challenge_wire = self.start()
        challenge = decode(challenge_wire, self.root, 1)
        keys = derive_keys(self.root, self.host, challenge.payload[32:], challenge.session)
        fields = dict(direction=0, kind=3, session=challenge.session,
                      sequence=1, challenge=challenge.challenge, payload=b"")
        for changes in (dict(session=b"x"*16), dict(challenge=b"x"*16),
                        dict(sequence=2), dict(payload=b"x"), dict(kind=5)):
            wire = encode(Envelope(**(fields | changes)), keys.c2b)
            self.assertEqual(self.receive(wire, 200)[0], 0)
            self.assertEqual(self.lib.phase(self.state), 1)
        self.assertEqual(self.receive(challenge_wire, 200)[0], 0)
        good = client.receive_challenge(challenge_wire, 200)
        self.assertEqual(self.receive(good, 300)[0], 1)

    def test_hello_requires_canonical_zero_fields(self):
        fields = dict(direction=0, kind=1, session=bytes(16), sequence=0,
                      challenge=bytes(16), payload=self.host)
        for changes in (dict(session=b"x"*16), dict(challenge=b"x"*16),
                        dict(sequence=1), dict(payload=b"x"*31), dict(kind=3)):
            wire = encode(Envelope(**(fields | changes)), self.root)
            self.assertEqual(self.receive(wire, 100)[0], 0)
            self.assertEqual(self.lib.phase(self.state), 0)
            self.assertEqual(self.rng_calls, 0)

    def test_each_rng_failure_clears_partial_state(self):
        hello = PilotAdmission(self.root, self.host).begin(100)
        for failure in (1, 2, 3):
            self.lib.lw_session_init(self.state)
            self.rng_calls = 0
            self.fail_rng_at = failure
            self.assertEqual(self.receive(hello, 100)[0], 2)
            self.assertEqual(self.lib.phase(self.state), 0)
            self.assertEqual(self.lib.retired_keys(self.state), 1)

    def test_failed_accept_encoding_retires_keys_and_cannot_reuse_claim(self):
        client, challenge = self.start()
        claim = client.receive_challenge(challenge, 200)
        self.assertEqual(self.lib.retired_keys(self.state), 0)
        self.assertEqual(self.receive(claim, 300, capacity=81)[0], 2)
        self.assertEqual(self.lib.phase(self.state), 0)
        self.assertEqual(self.lib.retired_keys(self.state), 1)
        self.assertEqual(self.receive(claim, 301)[0], 0)

    def test_rolling_pending_challenges_allow_claim_from_retained_slot(self):
        client, initial = self.start()
        self.assertEqual(self.issue(20099)[0], 0)
        rc, second = self.issue(20100)
        self.assertEqual(rc, 1)
        frame = decode(second, self.root, 1)
        first = decode(initial, self.root, 1)
        self.assertEqual(frame.payload, first.payload)
        self.assertEqual(frame.session, first.session)
        self.assertNotEqual(frame.challenge, first.challenge)
        self.assertEqual(frame.sequence, 0)
        # A later challenge does not invalidate an unexpired earlier one.
        claim = client.receive_challenge(initial, 20200)
        self.assertEqual(self.receive(claim, 20300)[0], 1)
        keys = derive_keys(self.root, self.host, frame.payload[32:], frame.session)
        rc, active = self.issue(40100)
        self.assertEqual(rc, 1)
        active = decode(active, keys.b2c, 1)
        self.assertEqual((active.kind, active.sequence, active.payload), (2, 2, b""))
        # Issuing more challenges must not renew receiver-input lifetime.
        self.assertEqual(self.lib.lw_session_tick(self.state, 100100), -1)

    def test_recent_rolling_challenge_can_admit_after_initial_one_expires(self):
        client, _ = self.start()
        for now in (20100, 40100, 60100, 80100):
            rc, latest = self.issue(now)
            self.assertEqual(rc, 1)
        claim = client.receive_challenge(latest, 80200)
        self.assertEqual(self.receive(claim, 80300)[0], 1)
        self.assertEqual(self.lib.lw_session_tick(self.state, 180099), 0)
        self.assertEqual(self.lib.lw_session_tick(self.state, 180100), -1)

    def test_challenge_generation_failure_retires_active_session(self):
        client, challenge = self.start()
        self.assertEqual(self.receive(client.receive_challenge(challenge, 200), 300)[0], 1)
        self.fail_rng = True
        self.assertEqual(self.issue(20100)[0], 2)
        self.assertEqual(self.lib.phase(self.state), 0)
        self.assertEqual(self.lib.retired_keys(self.state), 1)

    def test_session_memory_sanitizers(self):
        binary = Path(self.temp.name) / "session-memory"
        command = [arg for arg in self.compile_command[:-2] if arg not in ("-shared", "-fPIC")]
        command += [str(ROOT / "tests/pilot_session_memory_test.c"),
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    "-fno-omit-frame-pointer", "-o", str(binary)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_issuance_collision_capacity_and_sequence_exhaustion_retire(self):
        for failure in ("collision", "capacity", "sequence"):
            self.lib.lw_session_init(self.state)
            self.rng_calls = 0
            client, challenge = self.start()
            self.assertEqual(self.receive(client.receive_challenge(challenge, 200), 300)[0], 1)
            capacity = 594
            if failure == "collision":
                self.rng_calls = 2  # Next RNG output repeats initial challenge byte 3.
            elif failure == "capacity":
                capacity = 81  # Empty active envelope requires 82 bytes.
            else:
                self.lib.exhaust_sequence(self.state)
            with self.subTest(failure=failure):
                self.assertEqual(self.issue(20100, capacity=capacity)[0], 2)
                self.assertEqual(self.lib.phase(self.state), 0)
                self.assertEqual(self.lib.retired_keys(self.state), 1)
