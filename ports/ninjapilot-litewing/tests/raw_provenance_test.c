#include "litewing_raw_provenance.h"
#include <assert.h>
#include <string.h>

int main(void)
{
    struct lw_raw_batch batch = {0};
    struct lw_raw_sample sample = {
        .sequence=UINT32_MAX, .start_us=UINT32_MAX-4, .end_us=3,
        .bytes={0x80,0,0x7f,0xff,1,2,3,4,5,6,7,8,9,10}
    };
    lw_raw_append(&batch, &sample);
    sample.bytes[0]=0;
    assert(batch.samples[0].bytes[0]==0x80); /* Must copy, not alias. */
    assert(batch.samples[0].start_us==UINT32_MAX-4);
    assert(batch.samples[0].end_us==3);
    sample.sequence=0; lw_raw_append(&batch,&sample);
    sample.sequence=1; lw_raw_append(&batch,&sample);
    assert(batch.consumed==3 && batch.retained==3 && batch.flags==0);
    assert(batch.first_sequence==UINT32_MAX && batch.last_sequence==1);
    sample.sequence=3; lw_raw_append(&batch,&sample);
    assert(batch.consumed==4 && batch.retained==3);
    assert(batch.flags==(LW_RAW_TRUNCATED|LW_RAW_SEQUENCE_GAP));
    assert(batch.samples[2].sequence==1 && batch.last_sequence==3);
    batch.consumed=UINT16_MAX;
    sample.sequence=4; lw_raw_append(&batch,&sample);
    assert(batch.consumed==UINT16_MAX);
    assert(batch.flags & LW_RAW_COUNT_SATURATED);
    memset(&batch,0,sizeof batch);
    sample.sequence=50; lw_raw_append(&batch,&sample);
    assert(batch.flags==0 && batch.consumed==1 && batch.retained==1);
    assert(batch.first_sequence==50 && batch.last_sequence==50);
    assert(batch.samples[1].sequence==0);
    /* Queue trailer must survive a queue-style byte copy, without touching
     * the legacy prefix or requiring aligned access to its trailer. */
    unsigned char item[17 + sizeof(struct lw_raw_sample)];
    unsigned char received[sizeof item];
    memset(item,0xa5,sizeof item);
    lw_raw_queue_store(item,17,&sample);
    memcpy(received,item,sizeof item);
    memset(item,0,sizeof item);
    struct lw_raw_sample copied;
    lw_raw_queue_load(received,17,&copied);
    for (unsigned i=0;i<17;i++) assert(received[i]==0xa5);
    assert(copied.sequence==50 && copied.start_us==UINT32_MAX-4 && copied.end_us==3);
    assert(memcmp(copied.bytes,sample.bytes,14)==0);
    return 0;
}
