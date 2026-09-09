"""Restricted serial receiver-loss diagnostic, never an arming interface."""
import hashlib
import argparse
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import types

from receiver_contract import Evidence, FAST, NEUTRAL, READ_NAMES, SETTINGS, ProbeFailure

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'ai_assistant/src'))
from lrrk_litewing_ai.uavtalk import UAVTalkDecoder, UAVTalkError, crc8

PIN = 'ac77304a58de6c8bd552f94668b46903adb71cb2'
REVIEWED_APP = '3881b0feb5065fbe794ab4bd952bd149154da340d7edd951ed8bf4938bfba4c8'


def load_protocol(root):
    """Verify bytes, not just working-tree status, before importing upstream code."""
    root = root.resolve(strict=True)
    def git(*args):
        result = subprocess.run(['git','-C',str(root),*args], capture_output=True, check=True, timeout=10)
        return result.stdout
    if git('rev-parse','HEAD').decode().strip() != PIN:
        raise ProbeFailure('wrong upstream source revision')
    codec_path = 'ground/pyuavtalk/uavtalk.py'
    xml_path = 'shared/uavobjectdefinition'
    expected = set()
    verified = {}
    for entry in git('ls-tree','-r','-z',PIN,'--',codec_path,xml_path).split(b'\x00'):
        if not entry:
            continue
        metadata, relative = entry.decode().split('\t',1)
        if not (relative.endswith('.xml') or relative == codec_path):
            continue
        mode, kind, digest = metadata.split()
        path = root/relative
        if mode != '100644' or kind != 'blob' or path.is_symlink() or not path.is_file():
            raise ProbeFailure('unsafe protocol source file')
        data = path.read_bytes()
        actual = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\x00'+data).hexdigest()
        if actual != digest:
            raise ProbeFailure('protocol source content differs from pin')
        expected.add(relative)
        verified[relative] = data
    actual = {str(p.relative_to(root)) for p in (root/xml_path).glob('*.xml')}
    if actual | {codec_path} != expected:
        raise ProbeFailure('unexpected or missing XML definitions')
    # Never consult cached bytecode or reread a source after verifying it.
    codec = types.ModuleType('litewing_pinned_uavtalk')
    codec.__file__ = str(root/codec_path)
    exec(compile(verified[codec_path],codec.__file__,'exec'),codec.__dict__)
    db = codec.UAVObjectDB.__new__(codec.UAVObjectDB)
    db.by_name, db.by_id = {}, {}
    for relative in sorted(expected-{codec_path}):
        obj = codec._parse_object_xml(io.BytesIO(verified[relative]))
        if obj is not None:
            db.by_name[obj.name] = obj
            db.by_id[obj.obj_id] = obj
    return codec, db


class Wire:
    """Byte allowlist and strict framing with one bounded initial synchronization."""
    def __init__(self, codec, db):
        self.codec, self.db = codec, db
        self.requests = {name:codec.build_packet(0x21,db[name].obj_id,0) for name in READ_NAMES}
        obj = db['GCSTelemetryStats']
        self.status = {value:codec.build_packet(0x20,obj.obj_id,0,obj.pack({'Status':value})) for value in (1,3)}
        obj = db['GCSReceiver']
        self.neutral = codec.build_packet(0x20,obj.obj_id,0,obj.pack({'Channel':list(NEUTRAL)}))
        self.read_only = set(self.requests.values()) | set(self.status.values())
        self.acks = {codec.build_packet(0x23,obj.obj_id,0) for obj in db.by_id.values()}
        self.decoder = UAVTalkDecoder()
        self.initial = bytearray()
        self.synchronized = False
        self.discarded = 0
        self.settings_payloads = {}

    def validate_send(self, packet, allow_neutral=False):
        if not isinstance(packet, bytes) or not (packet in self.read_only or packet in self.acks or
                                               (allow_neutral and packet == self.neutral)):
            raise ProbeFailure('outbound packet outside neutral bench allowlist')

    def feed(self, data):
        if len(data) > 4096:
            raise ProbeFailure('serial read exceeds bound')
        if not self.synchronized:
            self.initial.extend(data)
            while self.initial:
                if self.discarded + len(self.initial) > 4352:
                    raise ProbeFailure('initial synchronization bound exceeded')
                if len(self.initial) < 4:
                    return []
                size = int.from_bytes(self.initial[2:4],'little')
                plausible = (self.initial[0] == 0x3c and self.initial[1] in (0x20,0x21,0x22,0x23,0x24,0xa0,0xa2)
                             and 10 <= size <= 229)
                if plausible and len(self.initial) < size+1:
                    return []
                if plausible and crc8(bytes(self.initial[:size])) == self.initial[size]:
                    self.synchronized = True
                    data = bytes(self.initial)
                    self.initial.clear()
                    break
                del self.initial[0]
                self.discarded += 1
                if self.discarded >= 4093:
                    raise ProbeFailure('no UAVTalk synchronization within 4096 bytes')
            if not self.synchronized:
                return []
        try:
            frames = self.decoder.feed(data)
        except (UAVTalkError, TypeError) as exc:
            raise ProbeFailure('invalid inbound framing: '+str(exc)) from exc
        decoded = []
        for frame in frames:
            obj = self.db.by_id.get(frame.object_id)
            if frame.message_type in (0x21,0x23,0x24):
                continue
            if obj is None:
                if frame.object_id-1 in self.db.by_id and len(frame.payload) == 8:
                    continue  # unsolicited metadata is never applied or written
                raise ProbeFailure('unknown inbound object')
            if len(frame.payload) != obj.size:
                raise ProbeFailure('known object payload size mismatch')
            if frame.instance_id != 0:
                # Other multi-instance objects may be periodic; selected safety
                # objects are all instance zero, and cannot be substituted.
                if obj.name in READ_NAMES:
                    raise ProbeFailure('nonzero safety-object instance')
                continue
            if obj.name in SETTINGS:
                if self.settings_payloads.setdefault(obj.name,frame.payload) != frame.payload:
                    raise ProbeFailure('settings payload bytes changed: '+obj.name)
            decoded.append((frame.message_type,obj,obj.describe(obj.unpack(frame.payload))))
        return decoded


class SerialLink:
    def __init__(self, wire, device, location):
        import serial
        from serial.tools import list_ports
        matches = [p for p in list_ports.comports() if p.device == device and
                   p.vid == 0x1a86 and p.pid == 0x7522 and p.location == location]
        if not device.startswith('/dev/cu.') or not location or len(matches) != 1:
            raise ProbeFailure('expected USB serial identity/location not present')
        self.wire = wire
        self.port = serial.Serial(port=None, baudrate=57600, timeout=0,
                                  write_timeout=.02, exclusive=True)
        try:
            self.port.dtr = self.port.rts = False
            self.port.port = device
            self.port.open()
        except BaseException:
            self.port.close()
            raise

    def send(self, packet, allow_neutral=False):
        self.wire.validate_send(packet, allow_neutral)
        if self.port.write(packet) != len(packet):
            raise ProbeFailure('incomplete serial write')

    def read(self):
        return self.port.read(min(max(self.port.in_waiting,1),4096))


def run_trial(wire, link, capture, clock=time.monotonic, sleep=time.sleep):
    """Run once with real or externally substituted I/O; always close owned port."""
    try:
        started = clock()
        evidence = Evidence(started)
    except BaseException:
        link.port.close()
        raise
    next_fast = next_settings = next_handshake = started
    gcs_status = 1
    total = 0
    digest = hashlib.sha256()
    counts = {}
    last_clock = started
    def bounded_now():
        nonlocal last_clock
        now = clock()
        if not math.isfinite(now) or now < last_clock:
            raise ProbeFailure('host monotonic clock regressed or invalid')
        last_clock = now
        if now-started >= 21.:
            raise ProbeFailure('total trial deadline exceeded')
        return now
    def checked_send(packet, allow_neutral=False):
        now = bounded_now()
        if evidence.phase != 'preflight':
            evidence.check(now)
        if allow_neutral:
            evidence.begin_input(now)
        link.send(packet, allow_neutral=allow_neutral)
        now = bounded_now()
        if evidence.phase != 'preflight':
            evidence.check(now)
    try:
        while not evidence.done:
            # Conservatively age the batch from before the nonblocking read.
            # Disk/decoder/ACK delays must never refresh old observations.
            received_at = bounded_now()
            data = link.read()
            bounded_now()
            if total+len(data) > 1024*1024:
                raise ProbeFailure('capture size bound exceeded')
            if capture.write(data) != len(data):
                raise ProbeFailure('incomplete private capture write')
            total += len(data)
            digest.update(data)
            frames = wire.feed(data)
            if bounded_now()-received_at > .75:
                raise ProbeFailure('stale inbound batch after I/O or decoding')
            # Observe all available frames before considering another input.
            acknowledgements = []
            for kind, obj, values in frames:
                if obj.name in READ_NAMES:
                    evidence.observe(obj.name,values,received_at)
                    counts[obj.name] = counts.get(obj.name,0)+1
                if kind in (0x22,0xa2):
                    acknowledgements.append(wire.codec.build_packet(0x23,obj.obj_id,0))
                if obj.name == 'FlightTelemetryStats' and values.get('Status') == 'HandshakeAck':
                    gcs_status = 3
            for packet in acknowledgements:
                checked_send(packet)
            now = bounded_now()
            if evidence.next_input(now):
                checked_send(wire.neutral, allow_neutral=True)
            if evidence.done:
                break
            if now >= next_handshake:
                checked_send(wire.status[gcs_status])
                next_handshake = now+1.
            if now >= next_fast:
                for name in FAST:
                    checked_send(wire.requests[name])
                next_fast = now+.2
            if now >= next_settings:
                for name in SETTINGS:
                    checked_send(wire.requests[name])
                next_settings = now+1.
            sleep(.005)
        # A valid prefix cannot certify an unresolved trailing safety update.
        wire.decoder.finish()
        result = evidence.result(bounded_now())
    except (Exception, KeyboardInterrupt) as exc:
        result = {'status':'FAIL', 'failure':type(exc).__name__+': '+str(exc),
                  'phase':evidence.phase, 'phases':evidence.phases,
                  'neutral_packets':evidence.sent, 'flight_ready':False}
    finally:
        link.port.close()
    try:
        now = bounded_now()
        if result['status'] == 'PASS_DISARMED_RECEIVER_OBSERVATIONS_ONLY':
            evidence.check(now)
    except (Exception,KeyboardInterrupt) as exc:
        result.update({'status':'FAIL','failure':type(exc).__name__+': '+str(exc),'flight_ready':False})
    result.update({'capture_bytes':total, 'capture_sha256':digest.hexdigest(),
                   'counts':counts, 'initial_discarded_bytes':wire.discarded,
                   'elapsed_host_s':last_clock-started})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flight-root',type=Path,required=True)
    parser.add_argument('--device',required=True)
    parser.add_argument('--location',required=True)
    parser.add_argument('--output',type=Path,required=True,help='new private directory, must not exist')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--props-removed',action='store_true')
    parser.add_argument('--battery-absent',action='store_true')
    parser.add_argument('--installed-app-sha256',help='operator attestation, not a device readback')
    args = parser.parse_args(argv)
    try:
        if not (args.execute and args.props_removed and args.battery_absent and
                args.installed_app_sha256 == REVIEWED_APP):
            raise ProbeFailure('explicit bench conditions and reviewed installed-app attestation required')
        codec, db = load_protocol(args.flight_root)
        wire = Wire(codec, db)
        args.output.mkdir(mode=0o700)  # exclusive; never reuse a previous trial
        def private_file(name, mode):
            fd = os.open(args.output/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            return os.fdopen(fd,mode)
        # Final report name is published only after both files flush/close.
        # A retained .pending file is explicitly not a completed report.
        with private_file('report.pending','w') as report:
            result = {}
            try:
                with private_file('capture.uavtalk','wb') as capture:
                    link = SerialLink(wire,args.device,args.location)
                    result = run_trial(wire,link,capture)
                    capture.flush()
                    os.fsync(capture.fileno())
            except (Exception,KeyboardInterrupt) as exc:
                result.update({'status':'FAIL','failure':type(exc).__name__+': '+str(exc),'flight_ready':False})
            result['operator_attested_app_sha256'] = args.installed_app_sha256
            json.dump(result,report,sort_keys=True,indent=2)
            report.write('\n')
            report.flush()
            os.fsync(report.fileno())
        os.link(args.output/'report.pending',args.output/'report.json')  # no overwrite
        (args.output/'report.pending').unlink()
        print(json.dumps(result,sort_keys=True))
        return 0 if result['status'] == 'PASS_DISARMED_RECEIVER_OBSERVATIONS_ONLY' else 2
    except (OSError,ProbeFailure,subprocess.SubprocessError) as exc:
        print('bench probe blocked: '+str(exc),file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
