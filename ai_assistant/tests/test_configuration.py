"""Configuration contracts: literal wire fixtures and real policy consumers."""
import importlib
import os
import re
import struct
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from lrrk_litewing_ai.models import TelemetrySnapshot
from lrrk_litewing_ai.safety import run_preflight
from lrrk_litewing_ai.uavobjects import snapshot_from_frame
from lrrk_litewing_ai.uavtalk import UAVTalkFrame, UAVTalkError
from lrrk_litewing_ai.approval import ApprovalStateMachine, ApprovalError
from lrrk_litewing_ai.tools import AssistantRuntime, get_latest_telemetry, compare_snapshots
from test_approval import snapshot, NOW

AXES = ('Manual', 'Rate', 'Attitude', 'AxisLock', 'WeakLeveling', 'VirtualBar',
        'Acro+', 'Rattitude', 'RelayRate', 'RelayAttitude', 'AltitudeHold',
        'AltitudeVario', 'CruiseControl')
SLOTS = (('Attitude', 'Attitude', 'Rate', 'Manual'),) * 6
FMS = 0x4D896486
SYS = 0xD9D093B8
FMS_BYTES = struct.pack('<5f3H', 10, .6, 30, 15, .98, 30000, 1000, 1000) + bytes([0] + [2, 2, 1, 0] * 6 + [1, 2, 3, 4, 5, 6, 0, 0])
SYS_BYTES = struct.pack('<4I2f', 1, 2, 3, 4, 30, 10) + bytes([5]) + b'PRIVATE-NAME'.ljust(20, b'\0') + bytes([0])


def decode(oid, payload, kind=0x20, instance=0):
    return snapshot_from_frame(UAVTalkFrame(kind, oid, instance, None, payload), NOW)


def mode_finding(state, delay=0):
    return next(f for f in run_preflight(state, now=NOW + timedelta(milliseconds=delay)).findings
                if f.finding_id == 'capabilities.mode')


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        # An explicit missing-feature assertion keeps the first RED diagnostic clear.
        self.assertIsNotNone(importlib.util.find_spec('lrrk_litewing_ai.configuration'),
                             'immutable configuration model is not implemented')
        self.model = importlib.import_module('lrrk_litewing_ai.configuration').ConfigurationObservation
        self.config = self.model(SLOTS, 'QuadX', 'Throttle', 0, 0)
        self.state = replace(snapshot(), flight_mode='stabilized1', configuration=self.config)

    def test_all_slots_select_the_observed_tuple(self):
        for selected in range(6):
            slots = list(SLOTS)
            slots[selected] = ('Rate', 'Attitude', 'Rate', 'CruiseControl')
            config = replace(self.config, stabilization_slots=tuple(slots))
            for mode in range(6):
                with self.subTest(selected=selected, mode=mode):
                    finding = mode_finding(replace(self.state, flight_mode='stabilized%d' % (mode + 1), configuration=config))
                    self.assertEqual(finding.status, 'UNKNOWN' if selected == mode else 'PASS')
                    if selected == mode:
                        self.assertIn('CruiseControl', finding.evidence)

    def test_unsupported_axes_cannot_inherit_generic_capabilities(self):
        for axis in range(4):
            for value in AXES:
                slot = list(SLOTS[0])
                slot[axis] = value
                config = replace(self.config, stabilization_slots=(tuple(slot),) * 6)
                expected = 'PASS' if value in (('Rate', 'Attitude') if axis < 3 else ('Manual',)) else 'UNKNOWN'
                with self.subTest(axis=axis, value=value):
                    self.assertEqual(mode_finding(replace(self.state, configuration=config, capabilities=('positioning', 'gps'))).status, expected)

    def test_missing_stale_and_unsupported_components(self):
        cases = [dict(stabilization_slots=()), dict(airframe_type=None), dict(thrust_control=None),
                 dict(airframe_type='QuadP'), dict(thrust_control='Collective'), dict(thrust_control='None')]
        for field in ('flight_mode_settings_age_ms', 'system_settings_age_ms'):
            cases.extend([{field: None}, {field: 2000}, {field: 2001}])
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertEqual(mode_finding(replace(self.state, configuration=replace(self.config, **changes))).status, 'UNKNOWN')
        self.assertEqual(mode_finding(replace(self.state, configuration=None)).status, 'UNKNOWN')
        for delay, expected in ((1999, 'PASS'), (2000, 'UNKNOWN')):
            self.assertEqual(mode_finding(self.state, delay).status, expected)
        for field in ('flight_mode_settings_age_ms', 'system_settings_age_ms'):
            state = replace(self.state, configuration=replace(self.config, **{field: 1999}))
            self.assertEqual(mode_finding(state, 1).status, 'UNKNOWN')

    def test_schema_roundtrip_and_legacy_cannot_smuggle_configuration(self):
        data = self.state.to_dict()
        self.assertEqual(data['schema_version'], 3)
        self.assertEqual(data['configuration']['stabilization_slots'], [list(s) for s in SLOTS])
        self.assertEqual(TelemetrySnapshot.from_json(self.state.to_json()), self.state)
        self.assertEqual(self.model.from_dict(self.config.to_dict()), self.config)
        for version in (1, 2):
            for config in (None, self.config.to_dict(), {'invalid': True}):
                legacy = TelemetrySnapshot.from_dict(dict(data, schema_version=version, configuration=config))
                self.assertIsNone(legacy.configuration)
                self.assertEqual(mode_finding(legacy).status, 'UNKNOWN')

    def test_model_is_immutable_and_rejects_bad_collections_enums_and_ages(self):
        with self.assertRaises(FrozenInstanceError):
            self.config.airframe_type = 'QuadP'
        for slots in ([], 'xxxx', (SLOTS[0],), (list(SLOTS[0]),) * 6, (('Rate',) * 3,) * 6,
                      (('unknown', 'Rate', 'Rate', 'Manual'),) * 6):
            with self.subTest(slots=slots), self.assertRaises(ValueError):
                replace(self.config, stabilization_slots=slots)
        for field in ('flight_mode_settings_age_ms', 'system_settings_age_ms'):
            for value in (True, '0', -1, float('nan'), float('inf')):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    replace(self.config, **{field: value})
        for field in ('airframe_type', 'thrust_control'):
            for value in ('unknown', 0, [], True):
                with self.assertRaises(ValueError):
                    replace(self.config, **{field: value})
        for value in ([], True, 'configuration', {'stabilization_slots': 'xxxx'}, {'stabilization_slots': [None] * 6}):
            with self.assertRaises(ValueError):
                self.model.from_dict(value)
        with self.assertRaises(ValueError):
            replace(self.state, configuration={})

    def test_exact_wire_decode_and_name_privacy(self):
        for kind in (0x20, 0x22, 0xA0, 0xA2):
            flight = decode(FMS, FMS_BYTES, kind)
            system = decode(SYS, SYS_BYTES, kind)
            self.assertEqual(flight.configuration, self.model(stabilization_slots=SLOTS, flight_mode_settings_age_ms=0))
            self.assertEqual(system.configuration, self.model(airframe_type='QuadX', thrust_control='Throttle', system_settings_age_ms=0))
            self.assertNotIn('PRIVATE', system.to_json())
        for kind in (0x21, 0x23, 0x24):
            self.assertIsNone(decode(FMS, FMS_BYTES, kind))

    def test_wire_rejects_every_enum_boundary_lengths_instances_and_nonfinite(self):
        for oid, payload, bounds, floats in (
            (FMS, FMS_BYTES, [(26, 11)] + [(i, 13) for i in range(27, 51)] + [(i, 18) for i in range(51, 57)] + [(57, 2), (58, 2)], range(0, 20, 4)),
            (SYS, SYS_BYTES, [(24, 21), (45, 3)], (16, 20)),
        ):
            for size in range(len(payload)):
                with self.assertRaises(UAVTalkError):
                    decode(oid, payload[:size])
            with self.assertRaises(UAVTalkError):
                decode(oid, payload + b'\0')
            with self.assertRaises(UAVTalkError):
                decode(oid, payload, instance=1)
            for offset, bound in bounds:
                bad = bytearray(payload)
                bad[offset] = bound
                with self.subTest(oid=oid, offset=offset), self.assertRaises(UAVTalkError):
                    decode(oid, bytes(bad))
            for offset in floats:
                bad = bytearray(payload)
                bad[offset:offset + 4] = struct.pack('<f', float('nan'))
                with self.assertRaises(UAVTalkError):
                    decode(oid, bytes(bad))

    def test_configuration_changes_invalidate_real_consumers_and_approvals(self):
        for changes in (dict(airframe_type='QuadP'), dict(thrust_control='Collective'),
                        dict(flight_mode_settings_age_ms=1), dict(system_settings_age_ms=1),
                        dict(stabilization_slots=(('Rate', 'Rate', 'Rate', 'Manual'),) * 6)):
            changed = replace(self.state, configuration=replace(self.config, **changes))
            self.assertNotEqual(changed.snapshot_hash(), self.state.snapshot_hash())
            before_report = run_preflight(self.state, now=NOW)
            after_report = run_preflight(changed, now=NOW)
            self.assertEqual(after_report.snapshot_hash, changed.snapshot_hash())
            self.assertNotEqual(before_report.snapshot_hash, after_report.snapshot_hash)
            comparison = compare_snapshots(self.state, changed)
            self.assertNotEqual(comparison['before_hash'], comparison['after_hash'])
            for approved in (False, True):
                runtime = AssistantRuntime(operator_session='test')
                runtime.ingest(self.state)
                runtime.last_report = before_report
                machine = runtime.approvals
                proposal = machine.create_proposal(self.state, 'inspect_telemetry', 'inspect', 'report', now=NOW)
                if approved:
                    machine.approve(proposal.proposal_id, 'human-confirmation', self.state, now=NOW)
                runtime.ingest(changed)
                self.assertIsNone(runtime.last_report)
                self.assertEqual(machine.state, 'ABORTED')
                self.assertFalse(machine.approval_is_current(changed, now=NOW))
                self.assertEqual(get_latest_telemetry(runtime)['snapshot']['configuration'], changed.configuration.to_dict())
            machine = ApprovalStateMachine('test')
            proposal = machine.create_proposal(self.state, 'inspect_telemetry', 'inspect', 'report', now=NOW)
            with self.assertRaises(ApprovalError):
                machine.approve(proposal.proposal_id, 'human-confirmation', changed, now=NOW)
            machine = ApprovalStateMachine('test')
            proposal = machine.create_proposal(self.state, 'inspect_telemetry', 'inspect', 'report', now=NOW)
            machine.approve(proposal.proposal_id, 'human-confirmation', self.state, now=NOW)
            self.assertFalse(machine.approval_is_current(changed, now=NOW))

    def test_old_analyzer_proposals_are_rejected(self):
        for approved in (False, True):
            machine = ApprovalStateMachine('test')
            with patch('lrrk_litewing_ai.safety.ANALYZER_VERSION', 'litewing-safety-3'):
                proposal = machine.create_proposal(self.state, 'inspect_telemetry', 'inspect', 'report', now=NOW)
                if approved:
                    machine.approve(proposal.proposal_id, 'human-confirmation', self.state, now=NOW)
            if approved:
                self.assertFalse(machine.approval_is_current(self.state, now=NOW))
            else:
                with self.assertRaises(ApprovalError):
                    machine.approve(proposal.proposal_id, 'human-confirmation', self.state, now=NOW)


class ConfigurationGeneratorTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('LW_IMU_GENERATOR'), 'set LW_IMU_GENERATOR for native generated interoperability')
    def test_pinned_xml_generated_structs_and_all_wire_enums(self):
        generator = Path(os.environ['LW_IMU_GENERATOR'])
        root = generator.parents[2]
        revision = 'ac77304a58de6c8bd552f94668b46903adb71cb2'
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            xml_dir = work / 'xml'
            xml_dir.mkdir()
            declarations = []
            for name, oid, fixture, offsets in (
                ('FlightModeSettings', FMS, FMS_BYTES,
                 {'Arming': 26, **{'Stabilization%dSettings' % i: 27 + 4 * (i - 1) for i in range(1, 7)},
                  'FlightModePosition': 51, 'DisableSanityChecks': 57, 'ReturnToBaseNextCommand': 58}),
                ('SystemSettings', SYS, SYS_BYTES, {'AirframeType': 24, 'ThrustControl': 45}),
            ):
                filename = name.lower()
                source = subprocess.run(['git', '-C', str(root), 'show',
                                         revision + ':shared/uavobjectdefinition/' + filename + '.xml'],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(source.returncode, 0, source.stderr)
                (xml_dir / (filename + '.xml')).write_text(source.stdout)
                generated = subprocess.run([str(generator), '-flight', str(xml_dir), str(root), name],
                                           cwd=work, capture_output=True, text=True, timeout=30)
                self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
                header = (work / 'flight' / (filename + '.h')).read_text()
                generated_oid = int(re.search(r'#define ' + name.upper() + r'_OBJID (\S+)', header).group(1), 0)
                self.assertEqual(generated_oid, oid)
                # Compile actual generated declarations, including the nested
                # four-axis structs. This catches layout/packing drift.
                declarations.append(re.search(r'typedef struct .*?' + name + r'Data;', header, re.S).group())
                existing = Path(os.environ['LW_IMU_EXISTING_HEADERS']) / (filename + '.h')
                existing_header = existing.read_text()
                self.assertEqual(re.search(r'typedef struct .*?' + name + r'Data;', existing_header, re.S).group(), declarations[-1])
                for field in ET.fromstring(source.stdout).findall('./object/field'):
                    if field.get('type') != 'enum':
                        continue
                    field_name = field.get('name')
                    options = field.get('options').split(',')
                    count = len(field.get('elementnames').split(',')) if field.get('elementnames') else int(field.get('elements', '1'))
                    generated_enum = re.search(r'typedef enum \{([^{}]+)\} ' + name + field_name + r'Options;', header).group(1)
                    self.assertEqual([int(v) for v in re.findall(r'=(\d+)', generated_enum)], list(range(len(options))))
                    for element in range(count):
                        offset = offsets[field_name] + element
                        for ordinal, symbol in enumerate(options):
                            payload = bytearray(fixture)
                            payload[offset] = ordinal
                            config = decode(generated_oid, bytes(payload)).configuration
                            if field_name.startswith('Stabilization'):
                                self.assertEqual(config.stabilization_slots[int(field_name[13]) - 1][element], symbol)
                            elif field_name == 'AirframeType':
                                self.assertEqual(config.airframe_type, symbol)
                            elif field_name == 'ThrustControl':
                                self.assertEqual(config.thrust_control, symbol)
                        payload[offset] = len(options)
                        with self.assertRaises(UAVTalkError):
                            decode(generated_oid, bytes(payload))
            probe = work / 'probe.c'
            probe.write_text('#include <stdint.h>\n#include <stdio.h>\n#include <string.h>\n' + '\n'.join(declarations) + '''
int main(void) {
    FlightModeSettingsDataPacked f = {0};
    SystemSettingsDataPacked s = {0};
    f.ReturnToBaseAltitudeOffset = 10; f.LandingVelocity = .6f;
    f.PositionHoldOffset.Horizontal = 30; f.PositionHoldOffset.Vertical = 15;
    f.VarioControlLowPassAlpha = .98f;
    f.ArmedTimeout = 30000; f.ArmingSequenceTime = 1000; f.DisarmingSequenceTime = 1000;
    f.Stabilization1Settings = (FlightModeSettingsStabilization1SettingsData){2, 2, 1, 0};
    f.Stabilization2Settings = (FlightModeSettingsStabilization2SettingsData){2, 2, 1, 0};
    f.Stabilization3Settings = (FlightModeSettingsStabilization3SettingsData){2, 2, 1, 0};
    f.Stabilization4Settings = (FlightModeSettingsStabilization4SettingsData){2, 2, 1, 0};
    f.Stabilization5Settings = (FlightModeSettingsStabilization5SettingsData){2, 2, 1, 0};
    f.Stabilization6Settings = (FlightModeSettingsStabilization6SettingsData){2, 2, 1, 0};
    for (int i = 0; i < 6; ++i) f.FlightModePosition[i] = i + 1;
    for (int i = 0; i < 4; ++i) s.GUIConfigData[i] = i + 1;
    s.AirSpeedMax = 30; s.AirSpeedMin = 10; s.AirframeType = 5;
    memcpy(s.VehicleName, "PRIVATE-NAME", 12);
    if (sizeof(f) != 59 || sizeof(s) != 46) return 1;
    if (fwrite(&f, 1, 59, stdout) != 59) return 2;
    return fwrite(&s, 1, 46, stdout) == 46 ? 0 : 3;
}
''')
            binary = work / 'probe'
            compiled = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(probe), '-o', str(binary)],
                                      capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            native = subprocess.run([str(binary)], capture_output=True, timeout=10)
            self.assertEqual(native.returncode, 0, native.stderr)
            self.assertEqual(native.stdout, FMS_BYTES + SYS_BYTES)
            self.assertEqual(decode(FMS, native.stdout[:59]).configuration.stabilization_slots, SLOTS)
            self.assertEqual(decode(SYS, native.stdout[59:]).configuration.airframe_type, 'QuadX')
