/* SPDX-License-Identifier: GPL-3.0-or-later
 * Only included by the pinned, generated USB UAVTalk translation unit.
 * Never register the secret request as a readable UAVObject.
 */
#include "pios_litewing_usb_maintenance.h"
#define LW_USB_SUBMIT_ID UINT32_C(0x4c575046)
#define LW_USB_STATUS_ID UINT32_C(0x4c575048)

static int lw_usb_reserved(uint32_t id)
{
    return id==LW_USB_SUBMIT_ID || id==LW_USB_STATUS_ID;
}

static void lw_usb_wipe_rx(UAVTalkConnectionData *connection)
{
    volatile uint8_t *p=connection->rxBuffer;
    for(size_t i=0;i<UAVTALK_MAX_PACKET_LENGTH;++i) p[i]=0;
}

/* Total frame lifetime, not an idle timer: trickled bytes cannot renew it.
 * Invoked by the sole receive task on data and idle ticks. No timer callback
 * races parser storage. The UART task's scheduling bounds cleanup latency. */
static int lw_usb_expire(UAVTalkConnectionData *connection)
{
    UAVTalkInputProcessor *p=&connection->iproc;
    if(p->state!=UAVTALK_STATE_INSTID && p->state!=UAVTALK_STATE_TIMESTAMP &&
       p->state!=UAVTALK_STATE_DATA && p->state!=UAVTALK_STATE_CS &&
       p->state!=UAVTALK_STATE_COMPLETE) return 0;
    if(!lw_usb_reserved(p->objId)) return 0;
    const int64_t now=esp_timer_get_time();
    if(p->usb_started_us<0 || now<p->usb_observed_us ||
       now-p->usb_started_us>=INT64_C(2000000)) {
        lw_usb_wipe_rx(connection);
        p->state=UAVTALK_STATE_SYNC;
        ++connection->stats.rxErrors;
        return 1;
    }
    p->usb_observed_us=now;
    return 0;
}

/* Caller owns the connection mutex. Replies contain no credential bytes and
 * never touch the generic object packer or its transmit buffer. */
static int32_t lw_usb_reply(UAVTalkConnectionData *connection,uint8_t type,uint32_t id,
                            const uint8_t *payload,uint8_t length)
{
    uint8_t wire[35]={0x3c,type,(uint8_t)(10+length),0,0,0,0,0,0,0};
    if(length>24 || !connection->outStream) {
        ++connection->stats.txErrors; return -1;
    }
    for(unsigned i=0;i<4;++i) wire[4+i]=(uint8_t)(id>>(i*8));
    if(length) memcpy(wire+10,payload,length);
    wire[10+length]=PIOS_CRC_updateCRC(0,wire,10+length);
    const int32_t total=11+length;
    const int32_t sent=connection->outStream(wire,total);
    if(sent!=total) {
        ++connection->stats.txErrors;
        connection->stats.txBytes+=(sent>0 ? sent : 0);
        return -1;
    }
    ++connection->stats.txObjects;
    connection->stats.txObjectBytes+=length;
    connection->stats.txBytes+=total;
    return 0;
}

static int32_t lw_usb_receive(UAVTalkConnectionData *connection)
{
    UAVTalkInputProcessor *p=&connection->iproc;
    int32_t result=-1;
    xSemaphoreTakeRecursive(connection->lock,portMAX_DELAY);
    if(lw_usb_expire(connection)) {
        xSemaphoreGiveRecursive(connection->lock);
        return -1;
    }
    /* A runtime collision disables BOTH routes, including an ordinary object
     * which later appears under either ID. Never unpack or expose that object. */
    const int collision=UAVObjGetByID(LW_USB_SUBMIT_ID)!=NULL ||
                        UAVObjGetByID(LW_USB_STATUS_ID)!=NULL;
    /* Registry lookup may wait for its mutex. It cannot extend frame life. */
    if(lw_usb_expire(connection)) {
        xSemaphoreGiveRecursive(connection->lock);
        return -1;
    }
    if(!collision && p->instId==0 && p->objId==LW_USB_SUBMIT_ID &&
       p->type==UAVTALK_TYPE_OBJ_ACK && p->length==152 && p->packet_size==162) {
        const int accepted=lw_usb_maintenance_submit(connection->rxBuffer,152)==0;
        const int32_t sent=lw_usb_reply(connection,accepted?UAVTALK_TYPE_ACK:UAVTALK_TYPE_NACK,
                                        p->objId,NULL,0);
        result=accepted ? sent : -1;
    } else if(!collision && p->instId==0 && p->objId==LW_USB_STATUS_ID &&
              p->type==UAVTALK_TYPE_OBJ_REQ && p->length==0 && p->packet_size==10) {
        uint8_t status[24];
        if(lw_usb_maintenance_status(status,sizeof(status))==24)
            result=lw_usb_reply(connection,UAVTALK_TYPE_OBJ,p->objId,status,sizeof(status));
        else
            (void)lw_usb_reply(connection,UAVTALK_TYPE_NACK,p->objId,NULL,0);
    } else if(p->type==UAVTALK_TYPE_OBJ_ACK || p->type==UAVTALK_TYPE_OBJ_REQ) {
        (void)lw_usb_reply(connection,UAVTALK_TYPE_NACK,p->objId,NULL,0);
    }
    /* Re-delivery of an already handled parsed packet is not another request.
     * UART ring/caller buffers have separate ownership and are not erased here. */
    lw_usb_wipe_rx(connection);
    p->state=UAVTALK_STATE_SYNC;
    xSemaphoreGiveRecursive(connection->lock);
    return result;
}
