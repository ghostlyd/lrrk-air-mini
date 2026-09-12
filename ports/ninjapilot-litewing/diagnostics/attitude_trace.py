"""Decode frozen estimator trace records; does not open hardware or issue commands."""
import struct

OBJECT_ID=0xC6CEDB44
WIRE=struct.Struct('<4I19f8H3H6B')

def decode(payload):
    if len(payload)!=WIRE.size: raise ValueError('trace v2 payload must be 120 bytes')
    v=WIRE.unpack(payload)
    count,trigger,index,version,state,available,known,suppression,reserved=v[31:]
    if (version!=2 or state not in range(4) or available not in (0,1) or
            known>15 or suppression>63 or reserved or index>=512 or count>512):
        raise ValueError('invalid trace header')
    if state==3:
        if count!=512 or trigger>64: raise ValueError('invalid frozen trace')
    else:
        if any(payload[:108]) or available or known or suppression:
            raise ValueError('incomplete trace must not expose sample data')
        if state==0 and count: raise ValueError('disabled trace has records')
        if state in (0,1) and (count>64 or trigger!=65535):
            raise ValueError('invalid rolling trace')
        if state==2 and not (trigger<=64 and trigger<count<512):
            raise ValueError('invalid posttrigger trace')
    requested=list(v[23:27]);submitted=list(v[27:31])
    if any(x>1000 for x in requested) or any(x>2047 for x in submitted):
        raise ValueError('invalid trace PWM range')
    if not available and (known or suppression or any(requested) or any(submitted)):
        raise ValueError('unavailable PWM contains unqualified data')
    if any(submitted[i] for i in range(4) if not known&(1<<i)):
        raise ValueError('unknown PWM channel is nonzero')
    # Preserve nonfinite sensor values: they are diagnostic evidence, not commands.
    return dict(timestamp_us=v[0]+(v[1]<<32),sequence=v[2],pwm_commits=v[3],
        dt=v[4],accel=list(v[5:8]),gyro=list(v[8:11]),corrected=list(v[11:14]),
        rpy=list(v[14:17]),pre_bias=list(v[17:20]),applied_bias=list(v[20:23]),
        requested=requested,submitted=submitted,count=count,
        trigger_index=trigger,record_index=index,state=state,pwm_available=bool(available),
        known_mask=known,suppression=suppression)

def validate_capture(records):
    if len(records)!=512: raise ValueError('capture requires all 512 records')
    trigger=records[0]['trigger_index']
    for i,r in enumerate(records):
        if (r['state']!=3 or r['count']!=512 or r['record_index']!=i or
                r['trigger_index']!=trigger):
            raise ValueError('capture indexes or frozen state mismatch')
        if i and (r['sequence']!=(records[i-1]['sequence']+1)&0xffffffff or
                  r['timestamp_us']<=records[i-1]['timestamp_us']):
            raise ValueError('capture sequence or device time discontinuity')
