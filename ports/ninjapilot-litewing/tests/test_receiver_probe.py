"""Host-only behavioral tests; no serial device is opened."""
import copy
import io
import os
import contextlib
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'diagnostics'))
try:
    import receiver_contract as contract
except ModuleNotFoundError:
    contract = None
try:
    import receiver_probe as probe
except ModuleNotFoundError:
    probe = None


def samples(connected=False):
    return {
        'FlightStatus': {'Armed': 'Disarmed', 'FlightMode': 'Stabilized1'},
        'ActuatorCommand': {'Channel': [0]*4+[1000]*8},
        'ManualControlCommand': {'Connected': 'True' if connected else 'False',
            'Channel': ([1000,1500,1500,1500,1000] if connected else [65535]*5)+[65534]*4,
            'Throttle': -1., 'Thrust': -1., 'Roll': 0., 'Pitch': 0., 'Yaw': 0.,
            'Collective': 0., 'FlightModeSwitchPosition': 0},
        'ManualControlSettings': {'ChannelGroups': ['GCS']*5+['None']*4,
            'ChannelNumber': [1,2,3,4,5,0,0,0,0], 'ChannelMin': [1000]*9,
            'ChannelNeutral': [1500]*9, 'ChannelMax': [2000]*9,
            'FailsafeChannel': [-1.,0.,0.,0.,0.,0.,0.,0.], 'FlightModeNumber': 3,
            'FailsafeFlightModeSwitchPosition': -1},
        'FlightModeSettings': {'Arming': 'Always Disarmed', 'DisableSanityChecks': 'FALSE',
            'FlightModePosition': ['Stabilized1','Stabilized2','Stabilized3','Stabilized4','Stabilized5','Stabilized6'],
            'Stabilization1Settings': ['Attitude','Attitude','Rate','Manual']},
        'ActuatorSettings': {'ChannelMin': [0]*4+[1000]*8,
            'ChannelNeutral': [0]*4+[1000]*8, 'ChannelMax': [1000]*12,
            'ChannelAddr': list(range(12)), 'ChannelType': ['PWM']*12,
            'MotorsSpinWhileArmed': 'FALSE'},
        'SystemSettings': {'AirframeType': 'QuadX', 'ThrustControl': 'Throttle'},
        'SystemAlarms': {'Alarm': ['OK','Uninitialised']+['OK']*5+['Warning']+['OK']*3+['Uninitialised']*3+['OK']+['Uninitialised']*6,
            'ExtendedAlarmStatus': ['None','None']},
    }


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(contract, 'receiver contract is not implemented')

    def fill(self, e, now, connected=False):
        for name, data in samples(connected).items():
            e.observe(name, data, now)

    def start(self):
        e=contract.Evidence(0.)
        self.fill(e, 0.)
        self.assertTrue(e.next_input(0.))
        return e

    def test_no_input_before_complete_preflight(self):
        e=contract.Evidence(0.)
        self.assertFalse(e.next_input(1.))
        with self.assertRaises(contract.ProbeFailure): e.next_input(15.)

    def test_unsafe_configuration_rejects_before_input(self):
        cases=[('FlightModeSettings','Arming','Yaw Right'),
            ('FlightModeSettings','DisableSanityChecks','TRUE'),
            ('SystemSettings','ThrustControl','Collective'),
            ('ManualControlSettings','ChannelNumber',[2,1,3,4,5,0,0,0,0]),
            ('ManualControlSettings','ChannelNeutral',[1000]*9),
            ('ActuatorSettings','MotorsSpinWhileArmed','TRUE'),
            ('ActuatorSettings','ChannelMin',[1]*12)]
        for name,field,value in cases:
            with self.subTest(field=field):
                e=contract.Evidence(0.); d=samples()[name];d[field]=value
                with self.assertRaises(contract.ProbeFailure):e.observe(name,d,0.)
                with self.assertRaises(contract.ProbeFailure):e.next_input(.1)

    def test_armed_nonzero_nan_and_short_payloads_latch_failure(self):
        for name,d in [('FlightStatus',{'Armed':'Armed','FlightMode':'Stabilized1'}),
                       ('ActuatorCommand',{'Channel':[0,0,1,0]+[1000]*8}),
                       ('ActuatorCommand',{'Channel':[0]*3}),
                       ('ActuatorCommand',{'Channel':[0,float('nan'),0,0]+[1000]*8})]:
            e=self.start()
            with self.assertRaises(contract.ProbeFailure):e.observe(name,d,.01)
            with self.assertRaises(contract.ProbeFailure):e.next_input(.04)

    def test_startup_zero_receiver_sample_does_not_open_input_gate(self):
        e=contract.Evidence(0.);self.fill(e,0.)
        d=samples()['ManualControlCommand'];d['Channel']=[0]*9;d['Throttle']=d['Thrust']=0.
        e.observe('ManualControlCommand',d,0.)
        self.assertFalse(e.next_input(.01))

    def test_initial_critical_alarm_blocks_until_a_fresh_nominal_sample(self):
        e=contract.Evidence(0.);self.fill(e,0.)
        d=samples()['SystemAlarms'];d['Alarm'][4]='Critical'
        e.observe('SystemAlarms',d,0.)
        self.assertFalse(e.next_input(.01))
        e.observe('SystemAlarms',samples()['SystemAlarms'],.02)
        self.assertTrue(e.next_input(.02))

    def test_active_critical_alarm_or_settings_change_aborts(self):
        for name,d in [('SystemAlarms',samples()['SystemAlarms']),('SystemSettings',samples()['SystemSettings'])]:
            e=self.start()
            if name=='SystemAlarms':d['Alarm'][4]='Critical'
            else:d['VehicleName']=[1]
            with self.assertRaises(contract.ProbeFailure):e.observe(name,d,.01)

    def test_stale_stream_and_clock_rollback_abort(self):
        e=self.start()
        with self.assertRaises(contract.ProbeFailure):e.check(.751)
        e=self.start()
        with self.assertRaises(contract.ProbeFailure):e.next_input(-.1)

    def test_missed_input_interval_aborts_without_catchup(self):
        e=self.start()
        self.assertFalse(e.next_input(.039))
        self.assertTrue(e.next_input(.04))
        with self.assertRaises(contract.ProbeFailure):e.next_input(.12)

    def test_missing_connection_never_passes_phase(self):
        e=self.start()
        with self.assertRaises(contract.ProbeFailure):
            for i in range(1,40):
                now=i*.04; self.fill(e,now);e.next_input(now)

    def test_four_real_observed_phases_required_for_pass(self):
        e=self.start(); sent=[0.]
        for i in range(1,130):
            now=i*.04
            # Expected state follows the previously observed phase, not the
            # implementation's packet/payload builders.
            connected=e.phase in ('input1','input2')
            self.fill(e,now,connected)
            if e.next_input(now):sent.append(now)
            if e.done:break
        self.assertTrue(e.done)
        result=e.result(now)
        self.assertEqual([p['phase'] for p in result['phases']],['input1','silence1','input2','silence2'])
        self.assertTrue(all(p['matches']>=3 for p in result['phases']))
        self.assertGreater(len(sent),50)
        with self.assertRaises(contract.ProbeFailure):contract.Evidence(0.).result(1.)


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=os.environ.get('LRRK_TEST_FLIGHT_ROOT')
        if not cls.root:raise unittest.SkipTest('pinned XML/codec tree not supplied')

    def setUp(self):
        self.assertIsNotNone(probe,'restricted protocol is not implemented')
        self.codec,self.db=probe.load_protocol(Path(self.root))
        self.wire=probe.Wire(self.codec,self.db)

    def test_only_exact_neutral_packet_and_permitted_reads_can_leave(self):
        self.wire.validate_send(self.wire.neutral, True)
        with self.assertRaises(contract.ProbeFailure):self.wire.validate_send(self.wire.neutral,False)
        self.assertEqual(self.db['GCSReceiver'].unpack(self.wire.neutral[10:-1])['Channel'],[1000,1500,1500,1500,1000,1500,1500,1500])
        for name in ('FlightStatus','SystemSettings'):
            with self.subTest(name=name):
                p=self.codec.build_packet(0x20,self.db[name].obj_id,0,self.db[name].pack({}))
                with self.assertRaises(contract.ProbeFailure):self.wire.validate_send(p,True)
        for channels in ([1200,1500,1500,1500,1000,1500,1500,1500],[1000,1600,1500,1500,1000,1500,1500,1500]):
            p=self.codec.build_packet(0x20,self.db['GCSReceiver'].obj_id,0,self.db['GCSReceiver'].pack({'Channel':channels}))
            with self.assertRaises(contract.ProbeFailure):self.wire.validate_send(p,True)
        with self.assertRaises(contract.ProbeFailure):self.wire.validate_send(self.wire.neutral[:-1]+b'\x00',True)

    def test_initial_sync_is_bounded_then_corruption_is_fatal(self):
        o=self.db['FlightStatus']; packet=self.codec.build_packet(0x20,o.obj_id,0,o.pack({}))
        frames=self.wire.feed(b'noise'+packet)
        self.assertEqual(len(frames),1)
        self.assertEqual(self.wire.discarded,5)
        with self.assertRaises(contract.ProbeFailure):self.wire.feed(b'noise'+packet)
        with self.assertRaises(contract.ProbeFailure):probe.Wire(self.codec,self.db).feed(b'x'*4096)

    def test_short_known_payload_and_nonzero_instance_rejected(self):
        for instance,payload in ((0,b'\x00'),(1,self.db['FlightStatus'].pack({}))):
            with self.subTest(instance=instance):
                w=probe.Wire(self.codec,self.db)
                packet=self.codec.build_packet(0x20,self.db['FlightStatus'].obj_id,instance,payload)
                with self.assertRaises(contract.ProbeFailure):w.feed(packet)

    def test_partial_frame_preserved_until_complete(self):
        packet=self.codec.build_packet(0x20,self.db['FlightStatus'].obj_id,0,self.db['FlightStatus'].pack({}))
        self.assertEqual(self.wire.feed(packet[:8]),[])
        self.assertEqual(len(self.wire.feed(packet[8:])),1)

    def trial(self, short_write=False, corrupt=False, stall=False):
        clock=type('Clock',(),{'now':0.,'__call__':lambda self:self.now})()
        wire=self.wire;codec=self.codec;db=self.db
        class Port:
            in_waiting=4096
            last_emit=-1.
            last_neutral=None
            closed=False
            writes=[]
            def write(self,data):
                self.writes.append((clock.now,data))
                if data==wire.neutral:self.last_neutral=clock.now
                return len(data)-1 if short_write else len(data)
            def read(self,n):
                if clock.now-self.last_emit<.05:return b''
                self.last_emit=clock.now
                state=samples(self.last_neutral is not None and clock.now-self.last_neutral<.1)
                packets=b''.join(codec.build_packet(0x20,db[name].obj_id,0,db[name].pack(data)) for name,data in state.items())
                if corrupt and clock.now>.1:return packets+b'bad'
                return packets
            def close(self):self.closed=True
        port=Port()
        link=probe.SerialLink.__new__(probe.SerialLink);link.port=port;link.wire=wire
        def sleep(delay):clock.now+=.2 if stall and port.last_neutral is not None else delay
        result=probe.run_trial(wire,link,io.BytesIO(),clock,sleep)
        return result,port

    def test_actual_runner_sends_only_neutral_and_observes_all_phases(self):
        self.assertTrue(hasattr(probe,'run_trial'),'trial runner not implemented')
        result,port=self.trial()
        self.assertEqual(result['status'],'PASS_DISARMED_RECEIVER_OBSERVATIONS_ONLY')
        self.assertTrue(port.closed)
        packets=[(at,p) for at,p in port.writes if p==self.wire.neutral]
        self.assertGreater(len(packets),50)
        for at,p in port.writes:self.wire.validate_send(p,True)
        for phase in result['phases']:
            if phase['phase'].startswith('silence'):
                self.assertFalse(any(phase['start_s']<=at<phase['end_s'] for at,p in packets))

    def test_write_corruption_and_scheduler_failure_close_without_retry(self):
        self.assertTrue(hasattr(probe,'run_trial'),'trial runner not implemented')
        for kwargs in ({'short_write':True},{'corrupt':True},{'stall':True}):
            with self.subTest(kwargs=kwargs):
                self.wire=probe.Wire(self.codec,self.db)
                result,port=self.trial(**kwargs)
                self.assertEqual(result['status'],'FAIL')
                self.assertTrue(port.closed)
                self.assertTrue(result['failure'])

    def test_serial_send_rejects_unapproved_packet_before_os_write(self):
        self.assertTrue(hasattr(probe,'SerialLink'),'serial guard not implemented')
        class Port:
            def write(self,p):raise AssertionError('unsafe packet reached OS')
        link=probe.SerialLink.__new__(probe.SerialLink);link.wire=self.wire;link.port=Port()
        with self.assertRaises(contract.ProbeFailure):link.send(self.wire.neutral)

    def test_cli_refuses_missing_attestations_before_serial_access(self):
        self.assertTrue(hasattr(probe,'main'),'CLI not implemented')
        with tempfile.TemporaryDirectory() as directory:
            args=['--flight-root',self.root,'--device','/dev/cu.example','--location','4-1',
                  '--output',str(Path(directory)/'new')]
            with patch.object(probe,'SerialLink') as serial,contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(probe.main(args),2)
                serial.assert_not_called()
                self.assertFalse((Path(directory)/'new').exists())

    def test_private_output_exclusivity_checked_before_serial_access(self):
        self.assertTrue(hasattr(probe,'main'),'CLI not implemented')
        with tempfile.TemporaryDirectory() as directory:
            args=['--flight-root',self.root,'--device','/dev/cu.example','--location','4-1',
                  '--output',directory,'--execute','--props-removed','--battery-absent',
                  '--installed-app-sha256','3881b0feb5065fbe794ab4bd952bd149154da340d7edd951ed8bf4938bfba4c8']
            with patch.object(probe,'SerialLink') as serial,contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(probe.main(args),2)
                serial.assert_not_called()

    def test_capture_short_write_fails_and_closes_owned_port(self):
        self.assertTrue(hasattr(probe,'run_trial'),'trial runner not implemented')
        class Port:
            closed=False
            def close(self):self.closed=True
        class Link:
            port=Port()
            def read(self):return b'a'
            def send(self,*args,**kw):raise AssertionError('no send after capture failure')
        class Capture:
            def write(self,data):return 0
        result=probe.run_trial(self.wire,Link(),Capture(),lambda:0.,lambda t:None)
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue(Link.port.closed)


if __name__=='__main__':unittest.main()
