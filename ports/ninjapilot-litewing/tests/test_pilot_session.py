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
            'int phase(struct lw_pilot_session *s) {return s->phase;}\n')
        command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                   '-DMBEDTLS_CONFIG_FILE="config.h"', "-I", str(out),
                   "-I", str(source / "include"), "-I", str(ROOT / "target/include")]
        command += [str(source / "library" / name) for name in ("md.c", "sha256.c", "hkdf.c", "platform_util.c")]
        command += [str(ROOT / "target" / name) for name in
                    ("litewing_pilot_session.c", "litewing_pilot_wire.c", "pios_litewing_pilot_mac.c", "pios_litewing_pilot_keys.c")]
        command += [str(out / "access.c"), "-o", str(out / "session.so")]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(out / "session.so"))
        cls.lib.state_size.restype = C.c_size_t
        cls.lib.phase.argtypes = [C.c_void_p]
        cls.lib.lw_session_init.argtypes = [C.c_void_p]
        cls.lib.lw_session_tick.argtypes = [C.c_void_p, C.c_int64]
        cls.lib.lw_session_receive.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t,
            C.c_void_p, C.c_int64, C.c_int, C.c_int, RNG, C.c_void_p,
            C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]

    def setUp(self):
        self.state = C.create_string_buffer(self.lib.state_size())
        self.lib.lw_session_init(self.state)
        self.root, self.host = b"r" * 32, b"h" * 32
        self.rng_calls = 0
        self.fail_rng = False
        def random(_ctx, dest, size):
            self.rng_calls += 1
            C.memset(dest, self.rng_calls, size)
            return -1 if self.fail_rng else 0
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
