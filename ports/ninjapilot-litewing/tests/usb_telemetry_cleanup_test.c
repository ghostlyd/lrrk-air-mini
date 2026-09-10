#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <setjmp.h>
#define lw_usb_uart_clear actual_clear
#include "litewing_usb_uart.h"
#undef lw_usb_uart_clear
static unsigned turns, reads, feeds, clears;
static jmp_buf done;
static int uavTalkCon=17;
static void lw_usb_uart_clear(uint8_t *data,size_t size) {
    actual_clear(data,size);
    for(size_t i=0;i<size;++i) assert(data[i]==0);
    ++clears;
}
static uint32_t getComPort(bool input) {
    assert(input);
    if(++turns==4) longjmp(done,1);
    return turns==3 ? 0 : 1;
}
static uint16_t PIOS_COM_ReceiveBuffer(uint32_t port,uint8_t *data,size_t size,unsigned wait) {
    assert(port==1 && size==16 && wait==500); ++reads;
    memset(data,0xa5,size); return reads==1 ? 16 : 0;
}
static int UAVTalkProcessInputStream(int connection,uint8_t *data,uint8_t size) {
    assert(connection==17); ++feeds;
    if(feeds==1) {
        assert(size==16 && data);
        for(unsigned i=0;i<16;++i) assert(data[i]==0xa5);
    } else assert(size==0);
    return 0;
}
static void vTaskDelay(unsigned ticks) { assert(ticks==5 && feeds==3 && clears==2); }
#include "task.inc"
int main(void) {
    if(!setjmp(done)) telemetryRxTask(NULL);
    assert(reads==2 && feeds==3 && clears==2);
    return 0;
}
