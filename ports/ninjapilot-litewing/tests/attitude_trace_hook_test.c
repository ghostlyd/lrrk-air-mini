/* Test the adapted estimator's capture boundary, not filter accuracy.
 * Substitute math services with known outputs to distinguish gyro arguments. */
#include <assert.h>
#include <math.h>
#include <stdbool.h>
#include <string.h>
#define M_PI_F 3.14159265f
typedef struct { float x,y,z; } AccelStateData;
typedef AccelStateData GyroStateData;
typedef struct { float q1,q2,q3,q4,Roll,Pitch,Yaw; } AttitudeStateData;
static int dtconfig, calls, writes;
static bool bad_norm, accel_filter_enabled;
static float q[4]={1,0,0,0}, accels_filtered[3],grot_filtered[3],gyro_correct_int[3];
static float accelKi,accelKp=.2f;
static float PIOS_DELTATIME_GetAverageSeconds(int *p) { (void)p; return .002f; }
static void apply_accel_filter(const float *a,float *b) { memcpy(b,a,12); }
static void CrossProduct(const float *a,const float *b,float *out)
{ (void)a;(void)b;out[0]=1;out[1]=2;out[2]=3; }
static float fast_invsqrtf(float x) { (void)x;return bad_norm?1001:1; }
static void quat_copy(const float *a,float *b) { memcpy(b,a,16); }
static void Quaternion2RPY(const float *q0,float *r)
{ (void)q0;r[0]=10;r[1]=11;r[2]=12; }
static void AttitudeStateGet(AttitudeStateData *s) { memset(s,0,sizeof *s); }
static void AttitudeStateSet(AttitudeStateData *s)
{ assert(s->Roll==10 && s->Pitch==11 && s->Yaw==12);++writes; }
#if CONFIG_LRRK_ATTITUDE_TRACE
static void LiteWingAttitudeTraceRecord(float dt,const float *a,const float *g,
                                        const float *c,const float *r)
{
    assert(writes==calls+1 && dt==.002f);
    assert(a[0]==1 && a[1]==2 && a[2]==3);
    assert(g[0]==4 && g[1]==5 && g[2]==6);
    assert(fabsf(c[0]-104)<.001 && fabsf(c[1]-205)<.001 && fabsf(c[2]-306)<.001);
    assert(r[0]==10 && r[1]==11 && r[2]==12);++calls;
}
#endif
#include "attitude_step.inc"
int main(void)
{
    AccelStateData a={1,2,3};GyroStateData g={4,5,6};
    updateAttitude(&a,&g);
    assert(writes==1 && calls==CONFIG_LRRK_ATTITUDE_TRACE);
    assert(g.x==4 && g.y==5 && g.z==6);
    bad_norm=true;updateAttitude(&a,&g);
    assert(writes==1 && calls==CONFIG_LRRK_ATTITUDE_TRACE);
    return 0;
}
