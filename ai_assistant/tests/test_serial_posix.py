import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace
try:
    from lrrk_litewing_ai import serial_posix as probe
except ImportError:
    probe = None

class ResetNeutralPosixPortTests(unittest.TestCase):
    def test_normal_transport_uses_reset_neutral_default(self):
        from lrrk_litewing_ai.live_uavtalk import SerialTelemetryTransport
        os_api, termios_api, fcntl_api, select_api = self.fixtures()
        constructor = probe.ResetNeutralPosixPort
        def open_port(device, baud):
            return constructor(device, baud, os_api=os_api,
                termios_api=termios_api, fcntl_api=fcntl_api,
                select_api=select_api)
        match = SimpleNamespace(device='/dev/cu.example', vid=0x1a86,
                                pid=0x7522, location='test')
        # No real driver may be reached by a host-only regression test.
        import sys
        legacy = SimpleNamespace(Serial=lambda **kw: self.fail('reset-prone serial factory used'))
        with patch.dict(sys.modules, {'serial': legacy, 'serial.tools':
                SimpleNamespace(list_ports=SimpleNamespace(comports=lambda: [match]))}), \
                patch.object(probe, 'ResetNeutralPosixPort', side_effect=open_port):
            transport = SerialTelemetryTransport(match.device, match.location,
                                                 comports=lambda: [match])
            transport.handshake(1)
            self.assertEqual(transport.read(3), b'inp')
            transport.close()
        self.assertEqual(fcntl_api.calls, [(17, termios_api.TIOCEXCL)])
        self.assertEqual(os_api.closed, [17])
        self.assertTrue(os_api.writes)

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
        with self.assertRaises(OSError):
            probe.ResetNeutralPosixPort('/dev/cu.example',57600,
                os_api=os_api,termios_api=termios_api,fcntl_api=fcntl_api,
                select_api=select_api,clock=lambda:0.)
        self.assertEqual(os_api.closed,[17])


