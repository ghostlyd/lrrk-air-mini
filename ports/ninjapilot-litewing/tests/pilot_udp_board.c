/* Test-only loopback peer. Real controller/crypto/receiver, synthetic platform. */
#define _POSIX_C_SOURCE 200809L
#include "uavobjectmanager.h"
#include "pios_gcsrcvr_priv.h"
#include "pios_litewing_gcsrcvr.h"
#include "litewing_pilot_controller.h"
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <time.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>

static GCSReceiverData storage;
UAVObjHandle GCSReceiverHandle(void) { return &storage; }
int32_t UAVObjUnpack(UAVObjHandle handle,uint16_t instance,const uint8_t *data)
{ (void)handle; (void)instance; (void)data; assert(0 && "wireless must not unpack objects"); return -1; }
int64_t esp_timer_get_time(void)
{
    struct timespec now;
    assert(clock_gettime(CLOCK_MONOTONIC,&now)==0);
    return (int64_t)now.tv_sec*1000000+now.tv_nsec/1000;
}
static int mapping(struct lw_pilot_channel out[5])
{
    for (unsigned i=0;i<5;++i) out[i]=(struct lw_pilot_channel){i+1,1000,1500,2000};
    return 0;
}
static int fixture_random(void *ctx,uint8_t *out,size_t size)
{ memset(out,++*(unsigned *)ctx,size); return 0; }
int main(int argc, char **argv)
{
    assert(argc==2 && (!strcmp(argv[1],"stop") || !strcmp(argv[1],"loss") ||
                      !strcmp(argv[1],"delayed-stop")));
    const int expect_loss=!strcmp(argv[1],"loss");
    uint32_t receiver;
    assert(PIOS_GCSRCVR_Init(&receiver)==0);
    struct lw_pilot_controller controller;
    lw_controller_init(&controller,NULL);
    int fd=socket(AF_INET,SOCK_DGRAM,0); assert(fd>=0);
    struct sockaddr_in local={.sin_family=AF_INET};
    assert(inet_pton(AF_INET,"127.0.0.1",&local.sin_addr)==1);
    assert(bind(fd,(struct sockaddr *)&local,sizeof(local))==0);
    socklen_t length=sizeof(local);
    assert(getsockname(fd,(struct sockaddr *)&local,&length)==0);
    printf("%u\n",ntohs(local.sin_port)); fflush(stdout);
    uint8_t root[32]; memset(root,'r',sizeof(root));
    unsigned random_counter=0;
    int published=0, have_peer=0;
    struct sockaddr_in peer={0};
    const int64_t started=esp_timer_get_time();
    while (esp_timer_get_time()-started<2000000) {
        fd_set readers; FD_ZERO(&readers); FD_SET(fd,&readers);
        struct timeval timeout={.tv_sec=0,.tv_usec=5000};
        int ready=select(fd+1,&readers,NULL,NULL,&timeout); assert(ready>=0);
        uint8_t wire[595], reply[594]; size_t written=0;
        if (ready) {
            struct sockaddr_in sender; socklen_t sender_size=sizeof(sender);
            ssize_t size=recvfrom(fd,wire,sizeof(wire),0,(struct sockaddr *)&sender,&sender_size);
            assert(size>=0);
            if (!strcmp(argv[1],"delayed-stop") && published && size>=7 && wire[6]==6) {
                const struct timespec delay={.tv_sec=0,.tv_nsec=120000000};
                assert(nanosleep(&delay,NULL)==0);
            }
            int64_t received=esp_timer_get_time();
            const int was_active=controller.session.phase==LW_ACTIVE;
            const int64_t input_origin=controller.session.challenge_us;
            enum lw_session_result result=lw_controller_receive_observed(&controller,
                wire,(size_t)size,root,received,mapping,fixture_random,&random_counter,
                reply,sizeof(reply),&written);
            if (result==LW_HANDSHAKE_REPLY) {
                peer=sender; have_peer=1;
                assert(sendto(fd,reply,written,0,(struct sockaddr *)&peer,sizeof(peer))==(ssize_t)written);
            }
            if (result==LW_PILOT_CANDIDATE) {
                const uint16_t expected[8]={1000,1500,1500,1500,1500,1000,2000,1234};
                for (unsigned i=0;i<8;++i) assert(pios_gcsrcvr_rcvr_driver.read(receiver,i)==expected[i]);
                published=1;
            }
            if (result==LW_RETIRED && published) {
                assert(!expect_loss);
                assert(size>=7 && wire[6]==6); /* Expected test's STOP transition. */
                const int64_t processed=esp_timer_get_time();
                assert(was_active && processed>=input_origin &&
                       processed-input_origin<100000 && "STOP input lease expired");
                assert(controller.owned && controller.session.phase==LW_CLOSED);
                assert(pios_gcsrcvr_rcvr_driver.read(receiver,0)==PIOS_RCVR_TIMEOUT);
                puts("PILOT_AND_STOP_VERIFIED");
                close(fd); return 0;
            }
        }
        if (have_peer) {
            enum lw_session_result result=lw_controller_challenge(&controller,root,
                fixture_random,&random_counter,reply,sizeof(reply),&written);
            if (result==LW_HANDSHAKE_REPLY)
                assert(sendto(fd,reply,written,0,(struct sockaddr *)&peer,sizeof(peer))==(ssize_t)written);
            if (result==LW_RETIRED) {
                assert(expect_loss && published && controller.owned);
                assert(controller.session.phase==LW_CLOSED);
                assert(pios_gcsrcvr_rcvr_driver.read(receiver,0)==PIOS_RCVR_TIMEOUT);
                puts("PILOT_AND_LOSS_VERIFIED");
                close(fd); return 0;
            }
        }
    }
    assert(0 && "interoperability deadline expired");
    close(fd); return 1;
}
