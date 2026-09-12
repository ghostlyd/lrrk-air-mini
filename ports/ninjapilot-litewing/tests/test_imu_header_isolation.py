"""Custom generation must not replace the pinned transport-wide aggregate."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ImuHeaderIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flight = os.environ.get('LRRK_TEST_FLIGHT_ROOT')
        if not flight:
            raise unittest.SkipTest('pinned flight checkout not supplied')
        cls.flight = Path(flight).resolve()
        generator = Path(os.environ.get('LW_IMU_GENERATOR',
            cls.flight / 'ground/uavobjgenerator/uavobjgenerator'))
        cls.directory = tempfile.TemporaryDirectory(prefix='lw-imu-isolation-')
        cls.addClassCleanup(cls.directory.cleanup)
        cls.out = Path(cls.directory.name)
        # Exercise the real preparer's existing API without modifying upstream.
        cls.upstream = cls.out / 'upstream'
        binary = cls.upstream / 'ground/uavobjgenerator/uavobjgenerator'
        binary.parent.mkdir(parents=True)
        binary.symlink_to(generator.resolve())
        (cls.upstream / 'flight').symlink_to(cls.flight / 'flight')
        corpus = cls.upstream / 'build/uavobject-synthetics'
        corpus.mkdir(parents=True)
        subprocess.run([str(generator), '-flight',
            str(cls.flight / 'shared/uavobjectdefinition'), str(cls.flight)],
            cwd=corpus, check=True, capture_output=True, text=True, timeout=30)
        cls.existing = corpus / 'flight'
        cls.custom = cls.out / 'custom'
        cls.custom.mkdir()
        # Reconfiguration must also work with the old aggregate still present
        # in an existing build directory. It must never be an include source.
        subprocess.run([str(generator), '-flight', str(ROOT / 'uavobjects'),
            str(cls.flight), 'LiteWingIMUHealth'], cwd=cls.custom,
            check=True, capture_output=True, text=True, timeout=30)
        subprocess.run([sys.executable, str(ROOT / 'prepare_imu_health.py'),
            '--upstream', str(cls.upstream), '--output', str(cls.custom)],
            check=True, capture_output=True, text=True, timeout=30)
        # Consume the actual custom include selection from CMake, including its
        # precedence over upstream. This also catches reverting that selection.
        cmake = (ROOT / 'esp-idf/main/CMakeLists.txt').read_text()
        includes = cmake.split('    INCLUDE_DIRS\n', 1)[1].split('    REQUIRES', 1)[0]
        custom_path = re.search(r'"\$\{LITEWING_IMU_DIR\}(/[^"\n]*)"', includes).group(1)
        cls.custom_include = Path(str(cls.custom) + custom_path)
        cls.parser = cls.out / 'parser'
        subprocess.run([sys.executable, str(ROOT / 'prepare_uavtalk.py'),
            '--source', str(cls.flight / 'flight/uavtalk'), '--output', str(cls.parser)],
            check=True, capture_output=True, text=True, timeout=30)
        cls.flags = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-Wno-unused-parameter', '-pthread',
            '-I', str(cls.custom_include), '-I', str(cls.existing),
            '-I', str(ROOT / 'tests/gcs_stubs'), '-I', str(ROOT / 'target/include'),
            '-I', str(cls.parser), '-I', str(cls.flight / 'flight/uavtalk/inc')]

    def test_real_parser_resolves_upstream_aggregate_and_corpus_bound(self):
        result = subprocess.run(self.flags + ['-dM', '-E', str(self.parser / 'uavtalk.c')],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        macro = r'^#define UAVOBJECTS_LARGEST (\d+)$'
        actual = int(re.search(macro, result.stdout, re.M).group(1))
        expected = int(re.search(macro, (self.existing / 'uavobjectsinit.h').read_text(), re.M).group(1))
        self.assertEqual(actual, expected, 'custom aggregate shadowed pinned transport bound')
        dependencies = subprocess.run(self.flags + ['-M', str(self.parser / 'uavtalk.c')],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(dependencies.returncode, 0, dependencies.stderr)
        self.assertIn(str(self.existing / 'uavobjectsinit.h'), dependencies.stdout)
        self.assertNotIn(str(self.custom / 'flight/uavobjectsinit.h'), dependencies.stdout)

        # Compile every real packed layout, independently of the aggregate's
        # size calculation. No hardcoded upstream maximum can mask truncation.
        declarations, checks = [], []
        headers = list(self.existing.glob('*.h')) + [self.custom_include / 'litewingimuhealth.h']
        for header in headers:
            if header.name == 'uavobjectsinit.h':
                continue
            text = header.read_text()
            declaration = text[text.index('typedef struct'):text.index('/* Typesafe')]
            name = re.search(r'(\w+DataPacked);', declaration).group(1)
            declarations.append(declaration)
            checks.append(f'_Static_assert(sizeof({name}) <= UAVOBJECTS_LARGEST, "{name}");')
        probe = self.out / 'bound.c'
        probe.write_text('#include <stdint.h>\n#include "uavobjectsinit.h"\n' +
            '\n'.join(declarations + checks) +
            '\n_Static_assert(sizeof(LiteWingIMUHealthDataPacked) == 9, "IMU wire size");\n'
            'int main(void) { return 0; }\n')
        result = subprocess.run(self.flags + [str(probe), '-o', str(self.out / 'bound')],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        subprocess.run([str(self.out / 'bound')], check=True, timeout=5)
        print(f'IMU_INCLUDE_BOUND=PASS bound={actual} layouts={len(checks)}')

    def test_only_custom_object_is_exposed_even_after_repeat_generation(self):
        original = {name: (self.existing / name).read_bytes()
                    for name in ('uavobjectsinit.h', 'uavobjectsinit.c')}
        for _ in range(2):
            subprocess.run([sys.executable, str(ROOT / 'prepare_imu_health.py'),
                '--upstream', str(self.upstream), '--output', str(self.custom)],
                check=True, capture_output=True, text=True, timeout=30)
            self.assertEqual({p.name for p in self.custom_include.iterdir()},
                             {'litewingimuhealth.h', 'litewingimuhealth.c',
                              'litewingimutiming.h', 'litewingimutiming.c'})
            self.assertEqual(original, {name: (self.existing / name).read_bytes()
                                        for name in original})

    def test_real_outbound_objects_larger_than_custom_imu(self):
        binary = self.out / 'protocol'
        result = subprocess.run(self.flags + [
            str(self.parser / 'uavtalk.c'), str(ROOT / 'target/pios_litewing_gcsrcvr.c'),
            str(ROOT / 'tests/gcs_session_unused.c'),
            str(ROOT / 'target/litewing_battery_pack.c'),
            str(ROOT / 'target/litewing_battery_voltage.c'),
            str(ROOT / 'target/litewing_wifi_config.c'),
            str(ROOT / 'tests/gcs_protocol_test.c'), '-o', str(binary)],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        for case in ('request-other', 'request-fresh'):
            with self.subTest(case=case):
                result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
