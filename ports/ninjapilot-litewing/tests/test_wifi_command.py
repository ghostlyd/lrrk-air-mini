"""Real owning-task/controller/receiver/crypto with bounded SDK/socket fixtures."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import selectors
import socket
import sys
import time
from test_pilot_crypto_vectors import PIN

ROOT = Path(__file__).resolve().parents[1]


class WifiCommandTests(unittest.TestCase):
    def test_real_task_failure_and_protocol_cases(self):
        path = os.environ.get('LRRK_TEST_MBEDTLS_ROOT')
        if not path:
            self.skipTest('pinned mbedTLS checkout not supplied; set LRRK_TEST_MBEDTLS_ROOT')
        crypto = Path(path)
        self.assertEqual(subprocess.check_output(
            ['git', '-C', str(crypto), 'rev-parse', 'HEAD'], text=True).strip(), PIN)
        self.assertEqual(subprocess.check_output(
            ['git', '-C', str(crypto), 'status', '--porcelain', '--untracked-files=no'], text=True), '')
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'command'
            command = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                       '-DMBEDTLS_CONFIG_FILE="crypto_config.h"']
            for include in (ROOT/'tests/wifi_command_stubs', ROOT/'tests/gcs_stubs',
                            ROOT/'target/include', crypto/'include'):
                command += ['-I', str(include)]
            command += [str(crypto/'library'/name) for name in
                        ('md.c', 'sha256.c', 'hkdf.c', 'platform_util.c')]
            command += [str(ROOT/'target'/name) for name in (
                'pios_litewing_wifi_command.c', 'litewing_pilot_session.c',
                'litewing_pilot_wire.c', 'pios_litewing_pilot_mac.c',
                'pios_litewing_pilot_keys.c', 'pios_litewing_gcsrcvr.c',
                'litewing_pilot_neutral.c')]
            command += [str(ROOT/'tests/wifi_command_test.c'), '-o', str(binary)]
            built = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(built.returncode, 0, built.stderr)
            cases = ('create', 'missing', 'netif', 'ip', 'zero-ip', 'not-up',
                     'socket', 'fcntl-get', 'fcntl-set', 'bind', 'getsockname',
                     'wrong-bind', 'hello-send', 'accept-send', 'challenge-send',
                     'recv-error', 'ap-fault', 'rng-fault', 'stop', 'loss',
                     'peer-replay', 'pending-peer', 'malformed', 'flood', 'time-budget',
                     'pending-expiry', 'cleanup', 'close-error', 'clock-rollback',
                     'admission-rollback')
            for case in cases:
                with self.subTest(case=case):
                    result = subprocess.run([str(binary), case], capture_output=True,
                                            text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
            for mode in ('loopback-stop', 'loopback-loss'):
                with self.subTest(case=mode):
                    self.loopback(binary, mode)

    def loopback(self, binary, mode):
        if sys.version_info < (3, 11):
            self.skipTest('operator loopback requires supported Python 3.11+; C cases still run')
        sys.path.insert(0, str(ROOT.parents[1]/'ai_assistant/src'))
        try:
            from lrrk_litewing_ai.pilot_udp import admit_udp
        finally:
            sys.path.pop(0)
        proc = subprocess.Popen([str(binary), mode], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        host = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        link = None
        try:
            host.bind(('127.0.0.1', 0))
            with selectors.DefaultSelector() as ready:
                ready.register(proc.stdout, selectors.EVENT_READ)
                self.assertTrue(ready.select(5), 'owning task did not bind loopback AP fixture')
            port = int(proc.stdout.readline().strip())
            host.connect(('127.0.0.1', port))
            sample = lambda: (1000,1500,1500,1500,1500,1000,2000,1234)
            link = admit_udp(host, b'r'*32, sample, lambda: time.monotonic_ns()//1000)
            self.assertTrue(any(link.step(sample) for _ in range(4)))
            if mode == 'loopback-stop': self.assertTrue(link.stop())
            stdout, stderr = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 0, stderr)
            self.assertIn('command task fixture passed', stdout)
        finally:
            if link is not None: link.close()
            host.close()
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=5)
