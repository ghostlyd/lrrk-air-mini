"""Host-only behavioral tests; no serial device is opened."""
import copy
import io
import os
import contextlib
import builtins
import importlib.machinery
import importlib.util
import marshal
import json
import struct
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
        self.assertTrue(self.step(e,0.))
        return e

    def step(self,e,now):
        due=e.next_input(now)
        if due:e.begin_input(now)
        return due

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
        self.assertFalse(self.step(e,.039))
        self.assertTrue(self.step(e,.04))
        with self.assertRaises(contract.ProbeFailure):self.step(e,.12)

    def test_missing_connection_never_passes_phase(self):
        e=self.start()
        with self.assertRaises(contract.ProbeFailure):
            for i in range(1,40):
                now=i*.04; self.fill(e,now);self.step(e,now)

    def test_early_matches_do_not_accept_a_phase_that_ends_disconnected(self):
        e=self.start()
        with self.assertRaises(contract.ProbeFailure):
            for i in range(1,31):
                now=i*.04
                self.fill(e,now,connected=i<=3)
                self.step(e,now)

    def test_four_real_observed_phases_required_for_pass(self):
        e=self.start(); sent=[0.]
        for i in range(1,130):
            now=i*.04
            # Expected state follows the previously observed phase, not the
            # implementation's packet/payload builders.
            connected=e.phase in ('input1','input2')
            self.fill(e,now,connected)
            if self.step(e,now):sent.append(now)
            if e.done:break
        self.assertTrue(e.done)
        result=e.result(now)
        self.assertEqual([p['phase'] for p in result['phases']],['input1','silence1','input2','silence2'])
        self.assertTrue(all(p['matches']>=3 for p in result['phases']))
        self.assertGreater(len(sent),50)
        with self.assertRaises(contract.ProbeFailure):contract.Evidence(0.).result(1.)

    def test_early_timeout_matches_do_not_accept_silence_ending_connected(self):
        e=self.start()
        for i in range(1,31):
            now=i*.04;self.fill(e,now,True);self.step(e,now)
        self.assertEqual(e.phase,'silence1')
        with self.assertRaises(contract.ProbeFailure):
            for i in range(31,61):
                now=i*.04;self.fill(e,now,connected=i>33);self.step(e,now)


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

    def test_verified_codec_cannot_be_replaced_by_unchecked_bytecode_cache(self):
        source=Path(self.root).resolve()/'ground/pyuavtalk/uavtalk.py'
        cache=importlib.util.cache_from_source(str(source))
        code=compile('CACHE_WAS_EXECUTED=True\nclass UAVObjectDB:\n def __init__(self,path): pass\n',str(source),'exec')
        pyc=importlib.util.MAGIC_NUMBER+struct.pack('<I',1)+b'\0'*8+marshal.dumps(code)
        original=importlib.machinery.SourceFileLoader.get_data
        def get_data(loader,path):
            return pyc if str(path)==cache else original(loader,path)
        with patch.object(importlib.machinery.SourceFileLoader,'get_data',get_data):
            codec,db=probe.load_protocol(Path(self.root))
        self.assertFalse(getattr(codec,'CACHE_WAS_EXECUTED',False))
        self.assertIn('FlightStatus',db)

    def test_xml_is_parsed_from_verified_bytes_not_a_second_filesystem_read(self):
        path=Path(self.root).resolve()/'shared/uavobjectdefinition/flightstatus.xml'
        replaced=path.read_bytes().replace(b'FlightStatus',b'PoisonedStatus')
        original=builtins.open
        def changed_open(file,*args,**kwargs):
            if str(file)==str(path):return io.BytesIO(replaced)
            return original(file,*args,**kwargs)
        with patch.object(builtins,'open',changed_open):
            codec,db=probe.load_protocol(Path(self.root))
        self.assertIn('FlightStatus',db)
        self.assertNotIn('PoisonedStatus',db)

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

    def test_settings_payload_bit_change_is_rejected_even_for_equal_float_values(self):
        obj=self.db['ManualControlSettings']
        values=samples()['ManualControlSettings']
        first=obj.pack(values)
        values['FailsafeChannel'][1]=-0.0
        second=obj.pack(values)
        self.assertNotEqual(first,second)
        self.assertEqual(obj.unpack(first),obj.unpack(second))
        self.wire.feed(self.codec.build_packet(0x20,obj.obj_id,0,first))
        with self.assertRaises(contract.ProbeFailure):
            self.wire.feed(self.codec.build_packet(0x20,obj.obj_id,0,second))

    def trial(self, short_write=False, corrupt=False, stall=False,
              capture_delay=0., final_delay=0., write_delay=0., trailing=False,
              cli_directory=None, close_failure=False, close_delay=0., decision_delay=0.):
        clock=type('Clock',(),{'now':0.,'__call__':lambda self:self.now})()
        wire=self.wire;codec=self.codec;db=self.db
        class Port:
            in_waiting=4096
            last_emit=-1.
            last_neutral=None
            tail_sent=False
            closed=False
            writes=[]
            def write(self,data):
                self.writes.append((clock.now,data))
                if data==wire.neutral:self.last_neutral=clock.now
                clock.now+=write_delay
                return len(data)-1 if short_write else len(data)
            def read(self,n):
                if self.tail_sent:return b''
                if clock.now-self.last_emit<.05:return b''
                self.last_emit=clock.now
                state=samples(self.last_neutral is not None and clock.now-self.last_neutral<.1)
                packets=b''.join(codec.build_packet(0x20,db[name].obj_id,0,db[name].pack(data)) for name,data in state.items())
                if corrupt and clock.now>.1:return packets+b'bad'
                if trailing and clock.now>4.6:
                    o=db['ActuatorCommand']
                    packets+=codec.build_packet(0x20,o.obj_id,0,o.pack({'Channel':[1]*12}))[:-1]
                    self.tail_sent=True
                return packets
            def close(self):
                self.closed=True
                clock.now+=close_delay
        port=Port()
        link=probe.SerialLink.__new__(probe.SerialLink);link.port=port;link.wire=wire
        def sleep(delay):clock.now+=.2 if stall and port.last_neutral is not None else delay
        class Capture(io.BytesIO):
            def write(self,data):
                clock.now+=capture_delay
                if data and clock.now>=4.7:clock.now+=final_delay
                return super().write(data)
        if cli_directory is None:
            original_next=probe.Evidence.next_input
            decisions=0
            def delayed_decision(e,now):
                nonlocal decisions
                decision=original_next(e,now)
                if decision:
                    decisions+=1
                    if decisions==2:clock.now+=decision_delay
                return decision
            with patch.object(probe.Evidence,'next_input',delayed_decision):
                result=probe.run_trial(wire,link,Capture(),clock,sleep)
        else:
            original_fdopen=os.fdopen
            original_trial=probe.run_trial
            class CloseFailure:
                def __init__(self,raw):self.raw=raw
                def __enter__(self):return self
                def __exit__(self,*args):self.close()
                def __getattr__(self,name):return getattr(self.raw,name)
                def close(self):
                    self.raw.close()
                    raise OSError('simulated final buffered capture flush failure')
            def fdopen(fd,mode):
                raw=original_fdopen(fd,mode)
                fail=(mode=='wb' and close_failure is True) or (mode=='w' and close_failure=='report')
                return CloseFailure(raw) if fail else raw
            args=['--flight-root',self.root,'--device','/dev/cu.example','--location','4-1',
                  '--output',str(cli_directory),'--execute','--props-removed','--battery-absent',
                  '--installed-app-sha256','3881b0feb5065fbe794ab4bd952bd149154da340d7edd951ed8bf4938bfba4c8']
            with patch.object(probe,'SerialLink',return_value=link),patch.object(probe.os,'fdopen',fdopen), \
                 patch.object(probe,'run_trial',lambda w,l,c:original_trial(w,l,c,clock,sleep)), \
                 contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                rc=probe.main(args)
            path=cli_directory/'report.json'
            result=json.loads(path.read_text()) if path.exists() else {'status':'NO_FINAL_REPORT'}
            result['exit_code']=rc
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

    def test_capture_delay_cannot_refresh_old_observations_or_authorize_input(self):
        result,port=self.trial(capture_delay=.8)
        self.assertEqual(result['status'],'FAIL')
        self.assertFalse(any(p==self.wire.neutral for at,p in port.writes))
        self.assertTrue(port.closed)

    def test_delay_in_final_silence_cannot_pass_beyond_total_deadline(self):
        result,port=self.trial(final_delay=22.)
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue(port.closed)

    def test_blocking_write_is_rechecked_before_more_output(self):
        result,port=self.trial(write_delay=22.)
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(len(port.writes),1)
        self.assertTrue(port.closed)

    def test_incomplete_actuator_frame_at_completion_prevents_pass(self):
        result,port=self.trial(trailing=True)
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('truncated frame',result['failure'])
        self.assertTrue(port.closed)

    def test_slow_port_close_cannot_publish_pass_beyond_total_deadline(self):
        result,port=self.trial(close_delay=22.)
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue(port.closed)

    def test_port_close_delay_cannot_pass_stale_final_observations(self):
        result,port=self.trial(close_delay=.8)
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('stale',result['failure'])
        self.assertTrue(port.closed)

    def test_overdue_input_decision_is_rejected_before_actual_write(self):
        result,port=self.trial(decision_delay=.05)
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual([at for at,p in port.writes if p==self.wire.neutral],[0.])
        self.assertTrue(port.closed)

    def test_short_decision_delay_does_not_create_catchup_burst(self):
        result,port=self.trial(decision_delay=.02)
        self.assertEqual(result['status'],'PASS_DISARMED_RECEIVER_OBSERVATIONS_ONLY')
        times=[at for at,p in port.writes if p==self.wire.neutral]
        self.assertTrue(all(b-a>=.04-1e-9 for a,b in zip(times,times[1:])))

    def test_initial_clock_failure_still_closes_owned_port(self):
        class Port:
            closed=False
            def close(self):self.closed=True
        class Link:
            port=Port()
        def failed_clock():raise OSError('clock unavailable')
        try:
            probe.run_trial(self.wire,Link(),io.BytesIO(),failed_clock,lambda t:None)
        except OSError:
            pass
        self.assertTrue(Link.port.closed)

    def test_capture_finalization_failure_cannot_publish_pass_report(self):
        with tempfile.TemporaryDirectory() as directory:
            result,port=self.trial(cli_directory=Path(directory)/'trial',close_failure=True)
            self.assertEqual(result['exit_code'],2)
            self.assertEqual(result['status'],'FAIL')
            self.assertTrue(port.closed)

    def test_success_report_describes_finalized_private_capture(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'trial'
            result,port=self.trial(cli_directory=output)
            self.assertEqual(result['exit_code'],0)
            data=(output/'capture.uavtalk').read_bytes()
            self.assertEqual(result['capture_bytes'],len(data))
            self.assertEqual(result['capture_sha256'],hashlib.sha256(data).hexdigest())
            self.assertEqual((output.stat().st_mode&0o777),0o700)
            for name in ('capture.uavtalk','report.json'):
                self.assertEqual(((output/name).stat().st_mode&0o777),0o600)

    def test_report_close_failure_cannot_publish_final_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'trial'
            result,port=self.trial(cli_directory=output,close_failure='report')
            self.assertEqual(result['exit_code'],2)
            self.assertFalse((output/'report.json').exists())
            self.assertTrue(port.closed)

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
