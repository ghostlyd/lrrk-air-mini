#!/usr/bin/env python3
"""Bounded macOS Gazebo -> native simlitewing probe. Never opens a serial port."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

from probe_contract import Evidence, ProbeFailure

PORT = Path(__file__).resolve().parents[1]
BOARD = "flight/targets/boards/simlitewing/board_hw_defs.c"


def git(checkout, *args):
    return subprocess.check_output(["git", "-C", str(checkout), *args])


def verify_source(checkout):
    manifest = json.loads((PORT / "SOURCE_MANIFEST.json").read_text())
    expected = manifest["sources"]["flight_tree"]["commit"]
    if git(checkout, "rev-parse", "HEAD").decode().strip() != expected:
        raise ProbeFailure("source revision does not match manifest")
    changed = set(git(checkout, "diff", "HEAD", "--name-only").decode().splitlines())
    if changed != {BOARD}:
        raise ProbeFailure("expected only the loopback source patch; found %r" % sorted(changed))
    original = git(checkout, "show", "HEAD:" + BOARD)
    # Fail on partial application and unrelated edits, not only on matching HEAD.
    if original.count(b'"0.0.0.0"') != 3 or (checkout / BOARD).read_bytes() != original.replace(b'"0.0.0.0"', b'"127.0.0.1"'):
        raise ProbeFailure("loopback configuration differs from reviewed patch")
    untracked = set(git(checkout, "ls-files", "--others", "--exclude-standard").decode().splitlines())
    if untracked - {"flight/targets/boards/litewing/LITEWING_CONTRACT.md"}:
        raise ProbeFailure("unexpected untracked source files")
    for patch in manifest["patches"]:
        if patch["source"] == "repository":
            path = PORT.parents[1] / patch["path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != patch["sha256"]:
                raise ProbeFailure("repository patch checksum mismatch")
    return expected


def check_free_ports():
    sockets = []
    try:
        for port in (9000, 9001, 9002):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sockets.append(s)
            s.bind(("0.0.0.0", port))
    except OSError as exc:
        raise ProbeFailure("simulator UDP port already in use; no existing process will be stopped") from exc
    finally:
        for s in sockets:
            s.close()


def owned_loopback_sockets(pid):
    result = subprocess.run(["lsof", "-nP", "-a", "-p", str(pid), "-i", "-Fn"], capture_output=True, text=True, timeout=5)
    names = [line[1:] for line in result.stdout.splitlines() if line.startswith("n")]
    if any(not name.startswith("127.0.0.1:") for name in names):
        raise ProbeFailure("native process has non-loopback network socket: %r" % names)
    return names


class GuardedTransport:
    """No target parameter and no serial fallback; only simulator sensor writes."""

    def __init__(self, db, capture):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.connect(("127.0.0.1", 9000))
        self.write_ids = {db[n].obj_id for n in ("GyroSensor", "AccelSensor", "GCSTelemetryStats")}
        self.capture = capture

    def send(self, data):
        kind = data[1]
        obj_id = int.from_bytes(data[4:8], "little")
        if kind not in (0x21, 0x23) and not (kind == 0x20 and obj_id in self.write_ids):
            raise ProbeFailure("blocked simulator write outside sensor/handshake allowlist")
        self.sock.send(data)

    def poll_recv(self, timeout):
        if not select.select([self.sock], [], [], timeout)[0]:
            return b""
        data = self.sock.recv(65536)
        self.capture.write(data)
        return data


def stop(proc):
    if proc is None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)


def run(checkout, output, sensor_dropout=False):
    source = verify_source(checkout)
    if sys.platform != "darwin" or not shutil.which("lsof"):
        raise ProbeFailure("runtime socket-ownership check currently requires macOS and lsof")
    check_free_ports()
    with (output / "build.log").open("w") as log:
        subprocess.run(["make", "-C", str(checkout), "fw_simlitewing_elf"], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    binary = checkout / "build/fw_simlitewing/fw_simlitewing.elf"
    sys.path.insert(0, str(checkout / "ground/pyuavtalk"))
    import uavtalk
    from uavtalk_client import UAVTalkClient
    import gz.transport13 as transport
    from gz.msgs10.imu_pb2 import IMU

    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("GZ_", "IGN_", "NINJAPILOT_", "LITEWING_")):
            del env[key]
    env.update(GZ_IP="127.0.0.1", GZ_PARTITION="lrrk-disarmed-" + output.name)
    # Gazebo's Python node reads this process environment too.
    os.environ.update({key: env[key] for key in ("GZ_IP", "GZ_PARTITION")})
    db = uavtalk.UAVObjectDB(str(checkout / "shared/uavobjectdefinition"))
    evidence, lock, done = Evidence(), threading.Lock(), threading.Event()
    native = server = worker = link = None
    sensor_stop_at = [float("inf")]
    with (output / "firmware.log").open("w") as fc_log, (output / "gazebo.log").open("w") as gz_log, (output / "telemetry.uavtalk").open("wb") as capture:
        try:
            native = subprocess.Popen([str(binary)], cwd=output, env=env, stdout=fc_log, stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 10
            while True:
                if native.poll() is not None:
                    raise ProbeFailure("native firmware exited during startup")
                sockets = owned_loopback_sockets(native.pid)
                if "127.0.0.1:9000" in sockets:
                    break
                if time.monotonic() > deadline:
                    raise ProbeFailure("native loopback telemetry socket did not start")
                time.sleep(0.1)
            link = GuardedTransport(db, capture)
            client = UAVTalkClient(link, db)

            def observed(obj, instance, data):
                if instance != 0:
                    return
                with lock:
                    evidence.observe(obj.name, data, time.monotonic())

            def receive():
                try:
                    while not done.is_set():
                        client.run(duration=0.25, on_object=observed)
                except Exception as exc:
                    with lock:
                        evidence.failure = str(exc)

            def imu(msg):
                if done.is_set() or time.monotonic() >= sensor_stop_at[0]:
                    return
                try:
                    a, w = msg.linear_acceleration, msg.angular_velocity
                    values = (a.x, a.y, a.z, w.x, w.y, w.z)
                    with lock:
                        evidence.imu(values, time.monotonic())
                    for name, xyz in (("GyroSensor", (math.degrees(w.x), -math.degrees(w.y), -math.degrees(w.z))), ("AccelSensor", (a.x, -a.y, -a.z))):
                        obj = db[name]
                        link.send(uavtalk.build_packet(uavtalk.TYPE_OBJ, obj.obj_id, 0, obj.pack(dict(zip(("x", "y", "z", "temperature"), (*xyz, 25.0))))))
                except Exception as exc:
                    with lock:
                        evidence.failure = str(exc)

            node = transport.Node()
            if not node.subscribe(IMU, "/litewing/imu", imu):
                raise ProbeFailure("Gazebo IMU subscription failed")
            worker = threading.Thread(target=receive, daemon=True)
            worker.start()
            world = checkout / "ground/gazebo_bridge/worlds/litewing.sdf"
            server = subprocess.Popen(["gz", "sim", "-s", "-r", "-v", "2", str(world)], cwd=output, env=env, stdout=gz_log, stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 20
            if sensor_dropout:
                sensor_stop_at[0] = deadline - 8
            while time.monotonic() < deadline:
                if native.poll() is not None or server.poll() is not None:
                    raise ProbeFailure("simulation process exited before the test completed")
                with lock:
                    if evidence.failure:
                        raise ProbeFailure(evidence.failure)
                for name in ("FlightStatus", "ActuatorCommand", "AttitudeState"):
                    client.request_object(name)
                time.sleep(0.05)
            with lock:
                result = evidence.result(time.monotonic())
            sockets = owned_loopback_sockets(native.pid)
            if "127.0.0.1:9000" not in sockets:
                raise ProbeFailure("native telemetry socket disappeared")
        finally:
            done.set()
            if worker:
                worker.join(timeout=2)
            try:
                stop(server)
            finally:
                try:
                    stop(native)
                finally:
                    if link:
                        link.sock.close()
    if evidence.failure:
        raise ProbeFailure(evidence.failure)
    logs = (output / "firmware.log").read_text(errors="replace")
    windows = [int(n) for n in re.findall(r"attitude: ok=(\d+)", logs)]
    if sum(n >= 10 for n in windows) < 3:
        raise ProbeFailure("firmware did not confirm three sensor-processing windows")
    result.update(source_commit=source, executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), native_sockets=sockets, attitude_sensor_ok_per_window=windows,
                  native_exit=native.returncode, gazebo_exit=server.returncode,
                  scope="native disarmed sensor ingestion; not full flight or ESP32 HAL verification")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="new evidence directory; must not already exist")
    parser.add_argument("--sensor-dropout", action="store_true", help="negative test: stop forwarding IMU after 12 seconds; expected result is FAIL")
    args = parser.parse_args()
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="lrrk-disarmed-"))
    if args.output:
        output.mkdir(parents=True, exist_ok=False)
    def interrupted(signum, frame):
        raise KeyboardInterrupt("probe interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    print("Evidence:", output, flush=True)
    try:
        result = run(args.checkout.resolve(), output, args.sensor_dropout)
    except (Exception, KeyboardInterrupt) as exc:
        result = {"status": "FAIL", "reason": str(exc) or type(exc).__name__}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
