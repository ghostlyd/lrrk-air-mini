"""Authenticated handshake fixtures; no sockets, keys, or board access."""
import unittest
from lrrk_litewing_ai.pilot_admission import PilotAdmission
from lrrk_litewing_ai.pilot_keys import derive_keys
from lrrk_litewing_ai.pilot_wire import Envelope, encode, decode


class AdmissionTests(unittest.TestCase):
    def test_fresh_claim_samples_are_authenticated_and_strict(self):
        client = self.make()
        samples = (1000, 1500, 1500, 1500, 1500, 1000, 2000, 1234)
        wire = client.receive_challenge(self.challenge_wire(), 200, samples)
        keys = derive_keys(self.root, self.host, self.board, self.session)
        self.assertEqual(decode(wire, keys.c2b, 0).payload,
                         b'\x03\xe8\x05\xdc\x05\xdc\x05\xdc\x05\xdc\x03\xe8\x07\xd0\x04\xd2')
        for samples in ((), (1500,)*7, (1500,)*9, (True,)*8, (999,)*8,
                        (2001,)*8, [1500]*8):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                self.make().receive_challenge(self.challenge_wire(),200,samples)

    root = b"r" * 32
    host = b"h" * 32
    board = b"b" * 32
    session = b"s" * 16
    challenge = b"c" * 16

    def make(self):
        client = PilotAdmission(self.root, self.host)
        hello = client.begin(100)
        self.assertEqual(decode(hello, self.root, 0),
                         Envelope(0, 1, bytes(16), 0, bytes(16), self.host))
        return client

    def challenge_wire(self, **changes):
        fields = dict(direction=1, kind=2, session=self.session, sequence=0,
                      challenge=self.challenge, payload=self.host + self.board)
        fields.update(changes)
        return encode(Envelope(**fields), self.root)

    def test_mutual_proof_before_established(self):
        client = self.make()
        keys = derive_keys(self.root, self.host, self.board, self.session)
        claim = client.receive_challenge(self.challenge_wire(), 200)
        self.assertFalse(client.established)
        self.assertEqual(decode(claim, keys.c2b, 0),
                         Envelope(0, 3, self.session, 1, self.challenge, b""))
        accept = encode(Envelope(1, 4, self.session, 1, self.challenge, b""), keys.b2c)
        client.receive_accept(accept, 300)
        self.assertTrue(client.established)
        with self.assertRaises(ValueError):
            client.receive_accept(accept, 301)

    def test_operator_handoff_requires_accept_and_is_single_use(self):
        client=self.make()
        with self.assertRaises(ValueError): client.take_operator_session(150)
        keys=derive_keys(self.root,self.host,self.board,self.session)
        client.receive_challenge(self.challenge_wire(),200,(1500,)*8)
        accept=encode(Envelope(1,4,self.session,1,self.challenge,b""),keys.b2c)
        client.receive_accept(accept,300)
        operator=client.take_operator_session(301)
        self.assertFalse(operator.closed)
        self.assertFalse(client.established)
        self.assertIsNone(client._keys)
        with self.assertRaises(ValueError): client.take_operator_session(302)

    def test_bad_board_proofs_cannot_advance(self):
        for changes in (dict(payload=b"x" * 64), dict(payload=self.host),
                        dict(sequence=1), dict(kind=7)):
            client = self.make()
            with self.assertRaises(ValueError):
                client.receive_challenge(self.challenge_wire(**changes), 200)
            self.assertFalse(client.established)
            self.assertIsInstance(client.receive_challenge(self.challenge_wire(), 201), bytes)
        client = self.make()
        wire = self.challenge_wire()
        with self.assertRaises(ValueError):
            client.receive_challenge(wire[:-1] + bytes([wire[-1] ^ 1]), 200)
        self.assertFalse(client.established)

    def test_accept_binds_session_challenge_sequence_and_role(self):
        keys = derive_keys(self.root, self.host, self.board, self.session)
        good = dict(direction=1, kind=4, session=self.session, sequence=1,
                    challenge=self.challenge, payload=b"")
        for changes in (dict(session=b"x"*16), dict(challenge=b"x"*16),
                        dict(sequence=2), dict(payload=b"x"), dict(kind=2)):
            client = self.make()
            client.receive_challenge(self.challenge_wire(), 200)
            with self.assertRaises(ValueError):
                client.receive_accept(encode(Envelope(**(good | changes)), keys.b2c), 300)
            self.assertFalse(client.established)
        for key in (self.root, keys.c2b, keys.telemetry):
            client = self.make()
            client.receive_challenge(self.challenge_wire(), 200)
            with self.assertRaises(ValueError):
                client.receive_accept(encode(Envelope(**good), key), 300)
            self.assertFalse(client.established)

    def test_expiry_rollback_and_close_prevent_reuse(self):
        for now in (99, 1000100):
            client = self.make()
            with self.assertRaises(ValueError):
                client.receive_challenge(self.challenge_wire(), now)
            with self.assertRaises(ValueError):
                client.receive_challenge(self.challenge_wire(), 201)
        client = self.make()
        client.close()
        with self.assertRaises(ValueError):
            client.begin(200)
        self.assertFalse(client.established)

    def test_strict_inputs_and_no_duplicate_hello(self):
        for value in (b"", b"x"*31, b"x"*33, None, "x"*32, bytearray(32)):
            with self.assertRaises(ValueError):
                PilotAdmission(value, self.host)
            with self.assertRaises(ValueError):
                PilotAdmission(self.root, value)
        for now in (-1, True, 1.0, None, 2**63):
            with self.assertRaises(ValueError):
                PilotAdmission(self.root, self.host).begin(now)
        client = self.make()
        with self.assertRaises(ValueError):
            client.begin(101)

    def test_accept_deadline_boundary_and_clock_rollback_retire_attempt(self):
        keys = derive_keys(self.root, self.host, self.board, self.session)
        accept = encode(Envelope(1, 4, self.session, 1, self.challenge, b""), keys.b2c)
        client = self.make()
        client.receive_challenge(self.challenge_wire(), 200)
        client.receive_accept(accept, 1_000_099)
        self.assertTrue(client.established)
        for now in (199, 1_000_100, 1_000_101):
            client = self.make()
            client.receive_challenge(self.challenge_wire(), 200)
            with self.assertRaises(ValueError):
                client.receive_accept(accept, now)
            self.assertFalse(client.established)
            # Retirement removes this object's credential references, not a
            # claim of Python memory zeroization.
            for name in ("_root", "_host", "_keys", "_session", "_challenge"):
                self.assertIsNone(getattr(client, name))
            with self.assertRaises(ValueError):
                client.receive_accept(accept, 300)
