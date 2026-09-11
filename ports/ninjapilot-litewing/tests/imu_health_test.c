#include "litewing_imu_health.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void check(struct lw_imu_observation observation, uint32_t now,
                  uint32_t timeout, const uint8_t expected[9])
{
    uint8_t guarded[11];
    memset(guarded, 0xa5, sizeof guarded);
    lw_imu_health_export(&observation, now, timeout, guarded + 1);
    assert(guarded[0] == 0xa5 && guarded[10] == 0xa5);
    assert(memcmp(guarded + 1, expected, 9) == 0);
}

int main(void)
{
    /* Literal wire fixtures catch premature failure/success and byte-order bugs. */
    check((struct lw_imu_observation){0}, 123, 100,
          (uint8_t[]){255,255,255,255,1,0,0,0,0});
    check((struct lw_imu_observation){true,0x68,false,true,99}, 123, 100,
          (uint8_t[]){255,255,255,255,1,1,0x68,0,0});
    check((struct lw_imu_observation){true,0x68,false,false,99}, 123, 100,
          (uint8_t[]){255,255,255,255,1,1,0x68,0,0});
    check((struct lw_imu_observation){true,0x68,true,true,100}, 199, 100,
          (uint8_t[]){99,0,0,0,1,1,0x68,1,1});
    check((struct lw_imu_observation){true,0x68,true,true,100}, 200, 100,
          (uint8_t[]){100,0,0,0,1,1,0x68,1,0});
    check((struct lw_imu_observation){true,0x68,true,true,100}, 201, 100,
          (uint8_t[]){101,0,0,0,1,1,0x68,1,0});
    check((struct lw_imu_observation){true,0x68,true,true,UINT32_MAX-15}, 16, 100,
          (uint8_t[]){32,0,0,0,1,1,0x68,1,1});
    check((struct lw_imu_observation){true,0x68,true,false,100}, 101, 100,
          (uint8_t[]){1,0,0,0,1,1,0x68,1,2});
    check((struct lw_imu_observation){false,0x42,true,false,100}, 200, 100,
          (uint8_t[]){100,0,0,0,1,0,0x42,1,2});
    check((struct lw_imu_observation){false,0x68,true,true,100}, 101, 100,
          (uint8_t[]){1,0,0,0,1,0,0x68,1,0});
    check((struct lw_imu_observation){true,0x68,true,true,100}, 100, 0,
          (uint8_t[]){0,0,0,0,1,1,0x68,1,0});
    check((struct lw_imu_observation){true,0x68,true,true,0}, 0x12345678, UINT32_MAX,
          (uint8_t[]){0x78,0x56,0x34,0x12,1,1,0x68,1,1});
    puts("IMU_HEALTH_NATIVE=PASS cases=12");
    return 0;
}
