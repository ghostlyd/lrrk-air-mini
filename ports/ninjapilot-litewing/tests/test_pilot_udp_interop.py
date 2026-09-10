"""Python client versus real C core, over loopback; no board or radio."""
import os
from pathlib import Path
import selectors
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from test_pilot_crypto_vectors import PIN

ROOT=Path(__file__).resolve().parents[1]

class InteropTests(unittest.TestCase):
    def test_sampled_admission_pilot_stop_against_real_c(self):
        path=os.environ.get('LRRK_TEST_MBEDTLS_ROOT')
        if not path: self.skipTest('pinned mbedTLS checkout not supplied')
        sdk=Path(path)
        self.assertEqual(subprocess.check_output(['git','-C',str(sdk),'rev-parse','HEAD'],text=True).strip(),PIN)
        self.assertEqual(subprocess.check_output(['git','-C',str(sdk),'status','--porcelain','--untracked-files=no'],text=True),'')
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            (out/'config.h').write_text('#define MBEDTLS_MD_C\n#define MBEDTLS_SHA256_C\n#define MBEDTLS_HKDF_C\n')
            binary=out/'board-peer'
            command=['cc','-std=c11','-Wall','-Wextra','-Werror','-pthread',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-DMBEDTLS_CONFIG_FILE="config.h"','-I',str(out),'-I',str(sdk/'include'),
                '-I',str(ROOT/'tests/gcs_stubs'),'-I',str(ROOT/'target/include')]
            command += [str(sdk/'library'/name) for name in ('md.c','sha256.c','hkdf.c','platform_util.c')]
            command += [str(ROOT/'target'/name) for name in ('litewing_pilot_session.c',
                'litewing_pilot_wire.c','pios_litewing_pilot_mac.c','pios_litewing_pilot_keys.c',
                'pios_litewing_gcsrcvr.c','litewing_pilot_controller.c','litewing_pilot_neutral.c')]
            command += [str(ROOT/'tests/pilot_udp_board.c'),'-o',str(binary)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            for mode in ('stop','loss'):
                with self.subTest(mode=mode): self.exchange(binary,mode)

    def exchange(self,binary,mode):
        sys.path.insert(0,str(ROOT.parents[1]/'ai_assistant/src'))
        try:
            from lrrk_litewing_ai.pilot_udp import admit_udp
        finally:
            sys.path.pop(0)
        proc=subprocess.Popen([str(binary),mode],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        host=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        link=None
        try:
            with selectors.DefaultSelector() as ready:
                ready.register(proc.stdout,selectors.EVENT_READ)
                self.assertTrue(ready.select(5),'C peer did not start')
            port=int(proc.stdout.readline().strip())
            host.connect(('127.0.0.1',port))
            clock=lambda:time.monotonic_ns()//1000
            samples=lambda:(1000,1500,1500,1500,1500,1000,2000,1234)
            link=admit_udp(host,b'r'*32,samples,clock)
            sent=False
            for _ in range(4):
                if link.step(samples): sent=True; break
            self.assertTrue(sent)
            if mode=='stop': self.assertTrue(link.stop())
            # Loss mode deliberately sends nothing further. Keep the socket open
            # to avoid making this a platform-specific ICMP error test.
            stdout,stderr=proc.communicate(timeout=5)
            self.assertEqual(proc.returncode,0,stderr)
            self.assertIn('PILOT_AND_'+mode.upper()+'_VERIFIED',stdout)
        finally:
            if link is not None: link.close()
            host.close()
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=5)
