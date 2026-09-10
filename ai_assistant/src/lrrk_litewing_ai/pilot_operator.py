"""Human-operator command session. Never expose this module to AI tools.

No sockets or credential discovery. Caller serializes access, supplies a monotonic
microsecond clock and samples a physical operator device. A returned frame is not
proof of transmission, acceptance, arming or flight. On send failure, close.
Python close drops references; it does not guarantee physical key zeroization.
"""
import struct
from .pilot_keys import SessionKeys
from .pilot_wire import Envelope, decode, encode
from .telemetry_session import TelemetrySession


class KeyboardInput:
    """Single-owner input for the documented LiteWing GCS channel profile.

    Channels 1..5 are throttle, roll, pitch, yaw, mode; endpoints 1000/2000,
    neutral 1500. This does not discover or verify aircraft configuration.
    Hold Space at minimum throttle to request existing yaw-right arming.
    No returned sample proves arming. GUI/session owner must stop on focus loss.
    Never share this mutable adapter across threads or expose it to AI tools.
    """

    def __init__(self):
        self._keys = set()
        self._last = None
        self._throttle = 1000.0
        self._enabled = False
        self.closed = False

    def press(self, key):
        key = key.lower() if key in {'W','S','A','D'} else key
        if key == 'Escape':
            self.stop()
        elif not self.closed and key in {'w','s','a','d','Left','Right','Up','Down','space'}:
            self._keys.add(key)

    def release(self, key):
        key = key.lower() if key in {'W','S','A','D'} else key
        self._keys.discard(key)

    def stop(self):
        self.closed = True
        self._keys.clear()

    def sample(self, now_us):
        if (self.closed or type(now_us) is not int or not 0 <= now_us < 2**63
                or (self._last is not None and not 0 <= now_us-self._last < 100_000)):
            self.stop()
            raise ValueError('keyboard input expired or stopped')
        elapsed = 0 if self._last is None else (now_us-self._last)/1_000_000
        self._last = now_us
        neutral = (1000,1500,1500,1500,1500,1500,1500,1500)
        if 'space' in self._keys and self._throttle == 1000:
            self._enabled = True
            return (1000,1500,1500,2000,1500,1500,1500,1500)
        if not self._enabled:
            return neutral
        def axis(negative, positive):
            return 1500 + 500 * ((positive in self._keys)-(negative in self._keys))
        self._throttle = min(2000., max(1000., self._throttle +
            250 * elapsed * (('w' in self._keys)-('s' in self._keys))))
        throttle = round(self._throttle)
        yaw = axis('a','d')
        # This profile scales throttle below neutral 1500 to negative values.
        # armhandler treats that entire range as low throttle, not just 1000.
        # Only explicit Space may issue the low-throttle yaw-right gesture.
        if throttle < 1500 and yaw > 1500:
            yaw = 1500
        return (throttle, axis('Left','Right'), axis('Up','Down'),
                yaw, 1500,1500,1500,1500)


class OperatorSession:
    def __init__(self, identity: bytes, keys: SessionKeys, now_us: int):
        if type(identity) is not bytes or len(identity)!=16 or type(keys) is not SessionKeys:
            raise ValueError("invalid operator session")
        if any(type(k) is not bytes or len(k)!=32 for k in (keys.c2b,keys.b2c,keys.telemetry)):
            raise ValueError("invalid operator keys")
        if type(now_us) is not int or not 0<=now_us<2**63:
            raise ValueError("invalid monotonic time")
        self._telemetry = TelemetrySession(identity, keys.telemetry)
        self._identity, self._keys = identity, keys
        self._last = self._proof_time = now_us
        self._board_sequence = self._sequence = 1
        self._challenge = None

    @property
    def closed(self): return self._keys is None

    def close(self):
        self._telemetry.close()
        self._identity = self._keys = None
        self._challenge = None

    def check_time(self, now_us):
        """Transport must call during silence; no input or lifetime renewal."""
        self._time(now_us)

    def observe_telemetry(self, datagram, received_us, received_at):
        """Return only key-free observations; telemetry never renews pilot proof.

        Like other operator methods, the owner must serialize calls. Receipt
        times are captured by that owner before processing the datagram.
        """
        self._time(received_us)
        return self._telemetry.receive(datagram, received_us, received_at)

    def _time(self, now):
        if self.closed: raise ValueError("operator session closed")
        if (type(now) is not int or not 0<=now<2**63 or now<self._last
                or now-self._proof_time>=100_000):
            self.close()
            raise ValueError("operator session expired or clock invalid")
        self._last=now

    def pilot(self, datagram, received_us, sample, clock):
        return self._respond(datagram,received_us,sample,clock,False)

    def stop(self, datagram, received_us, clock):
        """Requires a fresh authenticated challenge; retirement is unconditional
        after encoding. If no fresh proof exists, close and let board timeout.
        """
        return self._respond(datagram,received_us,None,clock,True)

    def _respond(self, datagram, received_us, sample, clock, stopping):
        try:
            now=clock()
        except BaseException:
            self.close()
            raise
        self._time(now)
        if (type(received_us) is not int or received_us<0 or received_us>now
                or now-received_us>75_000):
            self.close()
            raise ValueError("invalid challenge receive time")
        frame=decode(datagram,self._keys.b2c,1)
        reuse_stop=(stopping and frame.sequence==self._board_sequence
                    and frame.challenge==self._challenge)
        if (frame.kind!=2 or frame.payload or frame.session!=self._identity
                or (frame.sequence<=self._board_sequence and not reuse_stop)):
            raise ValueError("invalid or replayed board challenge")
        if reuse_stop:
            received_us=self._proof_time  # Never give a cached proof a new age.
        # Only authenticated fresh challenges may invoke the operator device.
        try:
            payload=b""
            if not stopping:
                values=sample()
                if (type(values) is not tuple or len(values)!=8
                        or any(type(v) is not int or not 1000<=v<=2000 for v in values)):
                    raise ValueError("invalid operator sample")
                payload=struct.pack("!8H",*values)
            end=clock()
            self._time(end)
            if end-received_us>75_000 or self._sequence>=2**64-2:
                raise ValueError("sample expired or command sequence exhausted")
            command=encode(Envelope(0,6 if stopping else 5,self._identity,
                self._sequence+1,frame.challenge,payload),self._keys.c2b)
            self._sequence+=1
            self._board_sequence=frame.sequence
            self._challenge=frame.challenge
            self._proof_time=received_us
            if stopping: self.close()
            return command
        except BaseException:
            self.close()
            raise
