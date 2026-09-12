#ifndef LRRK_PIOS_LITEWING_BRUSHED_PWM_H
#define LRRK_PIOS_LITEWING_BRUSHED_PWM_H

#include <stdbool.h>
#include <stdint.h>

#define LITEWING_PWM_SUPPRESS_HARDWARE (1u << 0)
#define LITEWING_PWM_SUPPRESS_IMU      (1u << 1)
#define LITEWING_PWM_SUPPRESS_LINK     (1u << 2)
#define LITEWING_PWM_SUPPRESS_DISARMED (1u << 3)
#define LITEWING_PWM_SUPPRESS_FAILSAFE (1u << 4)
#define LITEWING_PWM_SUPPRESS_SHUTDOWN (1u << 5)

/* Driver API results, NOT electrical duty measurements or shaft feedback.
 * requested: last frame consumed by Servo_Update, 0..1000.
 * submitted: last successful LEDC update/stop per channel, 0..2047.
 * A cleared known_mask bit makes submitted for that channel unknown.
 * Counters saturate. Snapshot uses a zero-wait mutex; false means unavailable.
 */
struct litewing_pwm_observation {
    uint16_t requested[4], submitted[4];
    uint32_t commits, write_errors, stop_errors;
    uint8_t known_mask, suppression;
    int64_t observed_us;
};
bool PIOS_LiteWing_BrushedPWM_GetObservation(struct litewing_pwm_observation *out);

int32_t PIOS_LiteWing_BrushedPWM_Init(void);
void PIOS_LiteWing_BrushedPWM_SetImuHealthy(bool healthy);
void PIOS_LiteWing_BrushedPWM_SetFailsafe(bool failsafe);
void PIOS_LiteWing_BrushedPWM_Shutdown(void);

#endif /* LRRK_PIOS_LITEWING_BRUSHED_PWM_H */
