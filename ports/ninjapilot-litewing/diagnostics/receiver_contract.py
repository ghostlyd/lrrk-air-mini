"""Neutral-only, disarmed bench evidence. No device or network access."""
import copy
import math

NEUTRAL = (1000, 1500, 1500, 1500, 1000, 1500, 1500, 1500)
SETTINGS = ('ManualControlSettings', 'FlightModeSettings', 'ActuatorSettings', 'SystemSettings')
FAST = ('FlightStatus', 'ActuatorCommand', 'ManualControlCommand', 'SystemAlarms')
READ_NAMES = SETTINGS + FAST + ('FlightTelemetryStats',)
PHASES = ('input1', 'silence1', 'input2', 'silence2')


class ProbeFailure(ValueError):
    pass


class Evidence:
    """One bounded four-phase trial; any failure is permanent for this instance.

    Times are host monotonic receipt times, not firmware measurement times.
    next_input consumes a send opportunity; the caller must abort on write error.
    """
    def __init__(self, now):
        if not math.isfinite(now):
            raise ProbeFailure('invalid start clock')
        self.started = self.clock = now
        self.latest = {}
        self.baseline = {}
        self.failure = None
        self.phase = 'preflight'
        self.phase_started = None
        self.phase_matches = 0
        self.phases = []
        self.last_send = None
        self.sent = 0
        self.done = False

    def reject(self, message):
        self.failure = self.failure or message
        raise ProbeFailure(self.failure)

    def tick(self, now):
        if self.failure:
            raise ProbeFailure(self.failure)
        if not math.isfinite(now) or now < self.clock:
            self.reject('host monotonic clock regressed or invalid')
        self.clock = now

    def require(self, condition, message):
        if not condition:
            self.reject(message)

    def observe(self, name, data, now):
        self.tick(now)
        if name not in READ_NAMES:
            return
        self.require(isinstance(data, dict), 'malformed object')
        if name == 'FlightStatus':
            self.require(data.get('Armed') == 'Disarmed', 'aircraft not disarmed')
            self.require(data.get('FlightMode') == 'Stabilized1', 'unexpected flight mode')
        elif name == 'ActuatorCommand':
            v = data.get('Channel')
            self.require(isinstance(v, list) and len(v) == 12 and
                         all(type(x) in (float, int) and math.isfinite(x) for x in v)
                         and v[:4] == [0]*4, 'nonzero or malformed motor commands')
        elif name in SETTINGS:
            self.validate_settings(name, data)
            if name in self.baseline:
                self.require(data == self.baseline[name], 'settings changed: ' + name)
            else:
                self.baseline[name] = copy.deepcopy(data)
        elif name == 'SystemAlarms':
            alarms = data.get('Alarm')
            self.require(isinstance(alarms, list) and len(alarms) == 21 and
                         all(x in ('Uninitialised','OK','Warning','Critical','Error') for x in alarms),
                         'malformed alarms')
            if self.phase != 'preflight':
                self.require(self.alarms_good(data), 'active bench alarm')
        elif name == 'ManualControlCommand':
            self.require(data.get('Connected') in ('True','False'), 'missing receiver connection')
            v = data.get('Channel')
            self.require(isinstance(v, list) and len(v) == 9 and
                         all(type(x) is int and 0 <= x <= 65535 for x in v), 'malformed receiver channels')
            for field in ('Throttle','Thrust','Roll','Pitch','Yaw','Collective'):
                value = data.get(field)
                self.require(type(value) in (int,float) and math.isfinite(value), 'invalid receiver axis')
            if self.phase != 'preflight':
                self.require(self.neutral_command(data), 'non-neutral receiver command')
                if now > self.phase_started and self.matches_phase(data):
                    self.phase_matches += 1
        self.latest[name] = (now, copy.deepcopy(data))

    def validate_settings(self, name, data):
        expected = {
            'ManualControlSettings': {'ChannelGroups': ['GCS']*5+['None']*4,
                'ChannelNumber': [1,2,3,4,5,0,0,0,0], 'ChannelMin': [1000]*9,
                'ChannelNeutral': [1500]*9, 'ChannelMax': [2000]*9,
                'FailsafeChannel': [-1.,0.,0.,0.,0.,0.,0.,0.], 'FlightModeNumber': 3,
                'FailsafeFlightModeSwitchPosition': -1},
            'FlightModeSettings': {'Arming': 'Always Disarmed', 'DisableSanityChecks': 'FALSE',
                'Stabilization1Settings': ['Attitude','Attitude','Rate','Manual']},
            'ActuatorSettings': {'ChannelMin': [0]*4+[1000]*8,
                'ChannelNeutral': [0]*4+[1000]*8, 'ChannelMax': [1000]*12,
                'ChannelAddr': list(range(12)), 'ChannelType': ['PWM']*12,
                'MotorsSpinWhileArmed': 'FALSE'},
            'SystemSettings': {'AirframeType': 'QuadX', 'ThrustControl': 'Throttle'},
        }[name]
        self.require(all(data.get(k) == v for k,v in expected.items()), 'unsafe settings: ' + name)
        if name == 'FlightModeSettings':
            modes = data.get('FlightModePosition')
            self.require(isinstance(modes, list) and len(modes) == 6 and modes[0] == 'Stabilized1',
                         'unsafe first mode')

    @staticmethod
    def alarms_good(data):
        alarms = data['Alarm']
        return (all(x not in ('Critical','Error') for x in alarms) and
                all(alarms[i] == 'OK' for i in (0,2,3,4,5,6,8,9,10,14)) and
                alarms[1] in ('OK','Uninitialised') and alarms[7] in ('OK','Warning') and
                data.get('ExtendedAlarmStatus') == ['None','None'])

    @staticmethod
    def neutral_command(data):
        return (data.get('Throttle') == -1 and data.get('Thrust') == -1 and
                all(data.get(k) == 0 for k in ('Roll','Pitch','Yaw','Collective')) and
                data.get('FlightModeSwitchPosition') == 0 and
                data['Channel'][:5] in (list(NEUTRAL[:5]), [65535]*5) and
                data['Channel'][5:] == [65534]*4)

    def matches_phase(self, data):
        connected = self.phase.startswith('input')
        return (data['Connected'] == ('True' if connected else 'False') and
                data['Channel'][:5] == (list(NEUTRAL[:5]) if connected else [65535]*5))

    def ready(self, now):
        return (all(name in self.latest and 0 <= now-self.latest[name][0] <=
                    (2.5 if name in SETTINGS else .75) for name in SETTINGS+FAST) and
                self.alarms_good(self.latest['SystemAlarms'][1]))

    def check(self, now):
        self.tick(now)
        self.require(self.ready(now), 'missing, stale or unhealthy bench observations')

    def next_input(self, now):
        self.tick(now)
        if self.done:
            return False
        if self.phase == 'preflight':
            self.require(now-self.started < 15., 'preflight deadline exceeded')
            if not self.ready(now):
                return False
            command = self.latest['ManualControlCommand'][1]
            if not (self.neutral_command(command) and command['Connected'] == 'False' and
                    command['Channel'][:5] == [65535]*5):
                return False
            self.phase, self.phase_started = PHASES[0], now
        self.check(now)
        if self.phase.startswith('input') and self.last_send is not None:
            self.require(now-self.last_send < .08-1e-9, 'missed neutral input cadence')
        if now-self.phase_started >= 1.2-1e-9:
            self.require(self.phase_matches >= 3, 'missing phase transition: ' + self.phase)
            self.phases.append({'phase':self.phase,'matches':self.phase_matches,
                'start_s':self.phase_started-self.started,'end_s':now-self.started})
            index = PHASES.index(self.phase)+1
            if index == len(PHASES):
                self.done = True
                return False
            self.phase, self.phase_started = PHASES[index], now
            self.phase_matches, self.last_send = 0, None
        if self.phase.startswith('input') and (self.last_send is None or now-self.last_send >= .04-1e-9):
            self.last_send = now
            self.sent += 1
            return True
        return False

    def result(self, now):
        self.check(now)
        self.require(self.done and len(self.phases) == 4, 'receiver-loss trial incomplete')
        return {'status':'PASS_DISARMED_RECEIVER_OBSERVATIONS_ONLY',
                'phases':copy.deepcopy(self.phases), 'neutral_packets':self.sent,
                'electrical_timing_verified':False, 'flight_ready':False}
