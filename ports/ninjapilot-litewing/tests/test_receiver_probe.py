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
              cli_directory=None, close_failure=False, close_delay=0., decision_delay=0.,
              tail_mode=None, tail_split=25, tail_chunk=4096, tail_delay=0.,
              completion_capture_delay=0.):
        clock=type('Clock',(),{'now':0.,'__call__':lambda self:self.now})()
        wire=self.wire;codec=self.codec;db=self.db
        class Port:
            in_waiting=4096
            last_emit=-1.
            last_neutral=None
            tail_sent=False
            tail_remainder=b''
            tail_reads=[]
            closed=False
            writes=[]
            def write(self,data):
                self.writes.append((clock.now,data))
                if data==wire.neutral:self.last_neutral=clock.now
                clock.now+=write_delay
                return len(data)-1 if short_write else len(data)
            def read(self,n):
                if self.tail_sent:
                    if not tail_mode or clock.now<4.805+tail_delay:return b''
                    self.tail_reads.append((clock.now,n))
                    amount=min(n,tail_chunk)
                    data=self.tail_remainder[:amount];self.tail_remainder=self.tail_remainder[amount:]
                    return data
                if clock.now-self.last_emit<.05:return b''
                self.last_emit=clock.now
                state=samples(self.last_neutral is not None and clock.now-self.last_neutral<.1)
                packets=b''.join(codec.build_packet(0x20,db[name].obj_id,0,db[name].pack(data)) for name,data in state.items())
                if corrupt and clock.now>.1:return packets+b'bad'
                if (trailing or tail_mode) and clock.now>4.6:
                    if tail_mode:
                        name='AttitudeState';values={}
                        if tail_mode=='armed':name='FlightStatus';values={'Armed':'Armed','FlightMode':'Stabilized1'}
                        if tail_mode=='motor':name='ActuatorCommand';values={'Channel':[1]*12}
                        if tail_mode=='reconnected':name='ManualControlCommand';values=samples(True)[name]
                        if tail_mode=='settings':
                            name='SystemSettings';values=samples()[name];values['ThrustControl']='Collective'
                        o=db[name];frame=codec.build_packet(0x22,o.obj_id,0,o.pack(values))
                        if tail_mode=='bad_crc':frame=frame[:-1]+bytes([frame[-1]^1])
                        # Tail includes a subsequent whole frame that must remain
                        # unread: completion ends at the already-open frame only.
                        self.tail_remainder=frame[tail_split:]+codec.build_packet(0x23,db['FlightStatus'].obj_id,0)
                        packets+=frame[:tail_split]
                    else:
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
                if port.tail_reads and data:clock.now+=completion_capture_delay
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

    def test_completes_only_pending_frame_without_any_further_writes(self):
        result,port=self.trial(tail_mode='safe')
        self.assertEqual(result['status'],'PASS_DISARMED_RECEIVER_OBSERVATIONS_ONLY')
        end=result['phases'][-1]['end_s']
        self.assertFalse(any(at>=end for at,p in port.writes))
        self.assertEqual([n for at,n in port.tail_reads],[14])
        self.assertEqual(port.tail_remainder,self.codec.build_packet(0x23,self.db['FlightStatus'].obj_id,0))
        self.assertEqual(result['completion']['additional_bytes'],14)
        self.assertTrue(port.closed)

    def test_partial_header_and_bytewise_tail_finish_at_same_boundary(self):
        for split in (1,2,3,4,25,38):
            with self.subTest(split=split):
                self.wire=probe.Wire(self.codec,self.db)
                result,port=self.trial(tail_mode='safe',tail_split=split,tail_chunk=1)
                self.assertEqual(result['status'],'PASS_DISARMED_RECEIVER_OBSERVATIONS_ONLY')
                self.assertEqual(len(port.tail_remainder),11)

    def test_serial_read_honors_explicit_limit(self):
        class Port:
            in_waiting=6
            data=io.BytesIO(b'abcdef')
            def read(self,n):return self.data.read(n)
        link=probe.SerialLink.__new__(probe.SerialLink);link.port=Port()
        try:data=link.read(2)
        except TypeError:self.fail('bounded serial read is not implemented')
        self.assertEqual(data,b'ab')
        for invalid in (0,-1,4097,True):
            with self.assertRaises(contract.ProbeFailure):link.read(invalid)
        self.assertEqual(link.read(),b'cdef')

    def test_missing_tail_and_late_capture_write_fail_completion_deadline(self):
        for kwargs in ({'tail_delay':.3},{'completion_capture_delay':.3}):
            with self.subTest(kwargs=kwargs):
                self.wire=probe.Wire(self.codec,self.db)
                result,port=self.trial(tail_mode='safe',**kwargs)
                self.assertEqual(result['status'],'FAIL')
                self.assertIn('completion deadline',result['failure'])
                self.assertTrue(port.closed)

    def test_completed_tail_still_checks_crc_armed_motor_and_settings(self):
        for mode,reason in (('bad_crc','CRC'),('armed','not disarmed'),
                            ('motor','motor commands'),('settings','payload bytes changed')):
            with self.subTest(mode=mode):
                self.wire=probe.Wire(self.codec,self.db)
                result,port=self.trial(tail_mode=mode,tail_split=1)
                self.assertEqual(result['status'],'FAIL')
                self.assertIn(reason,result['failure'])
                self.assertTrue(port.tail_reads)
                self.assertTrue(port.closed)

    def test_receiver_reconnection_in_completed_tail_prevents_pass(self):
        result,port=self.trial(tail_mode='reconnected',tail_split=1)
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('final receiver',result['failure'])
        self.assertTrue(port.closed)

    def test_failed_completion_preserves_byte_and_time_evidence(self):
        for mode,kwargs,expected_bytes in (('bad_crc',{},14),
                    ('safe',{'tail_delay':.3},0),('safe',{'completion_capture_delay':.3},14)):
            with self.subTest(mode=mode,kwargs=kwargs):
                self.wire=probe.Wire(self.codec,self.db)
                result,port=self.trial(tail_mode=mode,**kwargs)
                self.assertEqual(result['status'],'FAIL')
                self.assertIn('completion',result)
                completion=result['completion']
                self.assertEqual(completion['additional_bytes'],expected_bytes)
                self.assertGreater(completion['end_s'],completion['start_s'])
                self.assertFalse(completion['completed_pending_frame'])

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
            def read(self,max_bytes=4096):return b'a'
            def send(self,*args,**kw):raise AssertionError('no send after capture failure')
        class Capture:
            def write(self,data):return 0
        result=probe.run_trial(self.wire,Link(),Capture(),lambda:0.,lambda t:None)
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue(Link.port.closed)


class ResetNeutralPosixPortTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(probe, 'restricted protocol is not implemented')

    def fixtures(self, write_sizes=None, read_data=b'input'):
        class FakeOS:
            O_RDWR=2; O_NOCTTY=4; O_NONBLOCK=8
            opened=[]; closed=[]; writes=[]
            @classmethod
            def open(cls,path,flags):cls.opened.append((path,flags));return 17
            @classmethod
            def isatty(cls,fd):return fd==17
            @classmethod
            def close(cls,fd):cls.closed.append(fd)
            @classmethod
            def write(cls,fd,data):
                cls.writes.append((fd,bytes(data)))
                return (write_sizes.pop(0) if write_sizes else len(data))
            @classmethod
            def read(cls,fd,size):return read_data[:size]
        class FakeTermios:
            CSIZE=0x30; PARENB=0x100; CSTOPB=0x200; CS8=0x30
            CREAD=0x400; CLOCAL=0x800; CRTSCTS=0x1000
            B57600=57600; VMIN=5; VTIME=6; TCSANOW=0; TIOCEXCL=0x2000740d
            initial=[1,2,0x1330,4,9600,9600,[1,2,3,4,5,6,7]]
            applied=[]
            @classmethod
            def tcgetattr(cls,fd):return copy.deepcopy(cls.initial)
            @classmethod
            def tcsetattr(cls,fd,when,attrs):cls.applied.append((fd,when,copy.deepcopy(attrs)))
        class FakeFcntl:
            calls=[]
            @classmethod
            def ioctl(cls,fd,request):cls.calls.append((fd,request))
        class FakeSelect:
            calls=[]
            @classmethod
            def select(cls,read,write,error,timeout):
                cls.calls.append((read,write,error,timeout));return (read,write,error)
        return FakeOS,FakeTermios,FakeFcntl,FakeSelect

    def test_port_opens_exclusively_without_any_modem_line_ioctl(self):
        os_api,termios_api,fcntl_api,select_api=self.fixtures()
        port=probe.ResetNeutralPosixPort('/dev/cu.example',57600,
            os_api=os_api,termios_api=termios_api,fcntl_api=fcntl_api,
            select_api=select_api,clock=lambda:0.)
        self.assertEqual(os_api.opened,[('/dev/cu.example',14)])
        self.assertEqual(fcntl_api.calls,[(17,termios_api.TIOCEXCL)])
        attrs=termios_api.applied[0][2]
        self.assertEqual(attrs[:2],[0,0])
        self.assertEqual(attrs[3],0)
        self.assertEqual(attrs[4:6],[termios_api.B57600]*2)
        self.assertEqual(attrs[6][termios_api.VMIN],0)
        self.assertEqual(attrs[6][termios_api.VTIME],0)
        self.assertEqual(attrs[2]&termios_api.CRTSCTS,0)
        self.assertEqual(attrs[2]&(termios_api.CREAD|termios_api.CLOCAL|termios_api.CS8),
                         termios_api.CREAD|termios_api.CLOCAL|termios_api.CS8)
        self.assertEqual(port.read_available(3),b'inp')
        self.assertEqual(port.write(b'abc'),3)
        port.close();port.close()
        self.assertEqual(os_api.closed,[17])

    def test_partial_nonblocking_writes_complete_without_modem_controls(self):
        os_api,termios_api,fcntl_api,select_api=self.fixtures([1,2])
        ticks=iter((0.,0.,0.001,0.001))
        port=probe.ResetNeutralPosixPort('/dev/cu.example',57600,
            os_api=os_api,termios_api=termios_api,fcntl_api=fcntl_api,
            select_api=select_api,clock=lambda:next(ticks))
        self.assertEqual(port.write(b'abc'),3)
        self.assertEqual(os_api.writes,[(17,b'abc'),(17,b'bc')])

    def test_configuration_failure_closes_the_owned_descriptor(self):
        os_api,termios_api,fcntl_api,select_api=self.fixtures()
        termios_api.tcsetattr=classmethod(lambda cls,*args:(_ for _ in ()).throw(OSError('fail')))
        with self.assertRaises(contract.ProbeFailure):
            probe.ResetNeutralPosixPort('/dev/cu.example',57600,
                os_api=os_api,termios_api=termios_api,fcntl_api=fcntl_api,
                select_api=select_api,clock=lambda:0.)
        self.assertEqual(os_api.closed,[17])


if __name__=='__main__':unittest.main()
