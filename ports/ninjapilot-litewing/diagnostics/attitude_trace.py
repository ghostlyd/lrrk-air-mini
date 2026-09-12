"""Decode frozen estimator trace records; does not open hardware or issue commands."""
import struct

OBJECT_ID=0xE7AF695A
WIRE=struct.Struct('<15I19f12H50B')

def decode(payload):
    if len(payload)!=WIRE.size: raise ValueError('trace v3 payload must be 210 bytes')
    fields=WIRE.unpack(payload)
    # Normalize the unchanged estimator fields to their earlier tuple layout.
    v=fields[:4]+fields[15:45]+fields[46:52]
    count,trigger,index,version,state,available,known,suppression,reserved=v[31:]
    if (version!=3 or state not in range(4) or available not in (0,1) or
            known>15 or suppression>63 or reserved or index>=512 or count>512):
        raise ValueError('invalid trace header')
    if state==3:
        if count!=512 or trigger>64: raise ValueError('invalid frozen trace')
    else:
        if (any(payload[:152]) or any(payload[158:160]) or any(payload[166:])
                or available or known or suppression):
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
    consumed,retained,flags=fields[45],fields[94],fields[95]
    raw=[]
    if state==3:
        if (not consumed or retained!=min(consumed,3) or flags&~7 or
                bool(flags&1)!=(consumed>3) or (flags&2 and consumed!=65535)):
            raise ValueError('invalid raw provenance counts or flags')
        if fields[13]!=fields[4] or (consumed<=3 and fields[14]!=fields[3+retained]):
            raise ValueError('invalid raw provenance sequence bounds')
        span=(fields[14]-fields[13])&0xffffffff
        if (span>=0x80000000 or span<consumed-1 or
                (not flags&4 and not flags&2 and span!=consumed-1)):
            raise ValueError('incoherent raw sequence span')
        remaining=(fields[14]-fields[3+retained])&0xffffffff
        minimum_omitted=consumed-retained+bool(flags&2)
        if remaining>=0x80000000 or remaining<minimum_omitted:
            raise ValueError('raw sequence span cannot contain omitted samples')
        timestamp=v[0]+(v[1]<<32)
        for i in range(3):
            seq,start,end=fields[4+i],fields[7+i],fields[10+i]
            data=list(fields[52+i*14:66+i*14])
            if i>=retained:
                if seq or start or end or any(data):raise ValueError('unused raw slot is nonzero')
                continue
            if i:
                delta=(seq-fields[3+i])&0xffffffff
                if not 0<delta<0x80000000 or (delta!=1 and not flags&4):
                    raise ValueError('invalid raw sequence progression')
            if ((seq-fields[13])&0xffffffff)>span:
                raise ValueError('retained sequence exceeds last consumed')
            end_age=(v[0]-end)&0xffffffff
            duration=(end-start)&0xffffffff
            if end_age+duration>1000000 or end_age+duration>timestamp:
                raise ValueError('ambiguous raw read timestamp')
            raw.append(dict(sequence=seq,start_us=timestamp-end_age-duration,
                            end_us=timestamp-end_age,bytes=data))
            if len(raw)>1 and raw[-1]['start_us']<raw[-2]['end_us']:
                raise ValueError('overlapping or reversed raw reads')
    # Preserve nonfinite sensor values: they are diagnostic evidence, not commands.
    return dict(timestamp_us=v[0]+(v[1]<<32),sequence=v[2],pwm_commits=v[3],
        dt=v[4],accel=list(v[5:8]),gyro=list(v[8:11]),corrected=list(v[11:14]),
        rpy=list(v[14:17]),pre_bias=list(v[17:20]),applied_bias=list(v[20:23]),
        requested=requested,submitted=submitted,count=count,
        trigger_index=trigger,record_index=index,state=state,pwm_available=bool(available),
        known_mask=known,suppression=suppression,raw_samples=raw,
        raw_consumed=consumed,raw_flags=flags,raw_complete=state==3 and flags==0,
        raw_first=fields[13],raw_last=fields[14])

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
        if i:
            previous=records[i-1]
            delta=(r['raw_first']-previous['raw_last'])&0xffffffff
            if not 0<delta<0x80000000:
                raise ValueError('raw sample reuse or backtracking across records')
            if r['raw_samples'][0]['start_us']<previous['raw_samples'][-1]['end_us']:
                raise ValueError('raw reads overlap across records')
