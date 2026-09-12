# Normal-mixer comparison: gyro event reproduced

Application source: `ef45140276c2fb3bde16cfeecb1643177d692ab6`.
Application SHA-256:
`48ef6820436976e29804a81fe31cd663c290e177d7539f535fc25784995ab035`.
Exact application-only readback passed; recovery and settings regions were
preserved. Both fixed-output modes were disabled, while the 200/1000 per-motor
ceiling, ten-second nonrenewing cutoff, and attitude recorder remained enabled.

The successful transaction completed with positive PWM receipts spanning
9.682 seconds, followed by shutdown, zero output, and no driver errors.
The operator observed smooth rotation, but inconsistent speed and duration.
This is not a measured RPM record. The prior
fixed-all trial was confirmed by the operator as smooth continuous rotation.

Two earlier startup attempts did not reach arming: one sent a neutral command
before the handshake completed; another sent no controls and encountered a
bad-CRC frame after one valid frame. The runner now requires fresh Connected
telemetry before controls. A subsequent request-only check and the final trial
passed without loosening CRC validation. The isolated corruption is unexplained.

## Trace comparison

After timeout disarming, request-only retrieval verified zero output and
recovered all 512 frozen records spanning 1.005629 seconds.

- Normal mixer peak absolute gyro: 273.4043 degrees/s, versus 1.2964 degrees/s
  in the fixed-all capture. Fourteen normal-mixer samples exceeded 20 degrees/s.
- First event: index 87, 36.597 ms after trigger, gyro-X -118.3433 degrees/s,
  recorded PWM `[0,8,0,8]` on the 0..2047 LEDC scale.
- Peak: index 88, 38.473 ms after trigger, gyro-X -273.4043 degrees/s,
  recorded PWM `[409,0,0,409]`.
- Maximum recorded per-channel PWM before the first event: `[39,12,6,10]`.
- All recorded gyro, accelerometer and attitude values were finite. Roll ranged
  -1.550 to -0.154 degrees; pitch 4.390 to 4.635 degrees.

The recorded high-output response follows the first large gyro sample. The
trace does not support attributing that sample to a preceding high-output
command, but PWM and sensors are independently sampled, not electrically
synchronized. Fixture motion, low-duty motor vibration, electrical interference,
and acquisition defects remain distinguishable hypotheses, not established causes.
Do not suppress gyro data or retune PID to hide this event. The recorded dt is
averaged estimator timing, not raw acquisition timing.

Next correlate the operator observation with this event and inspect the sensor
acquisition path before selecting another powered experiment. Raw captures stay
private outside Git. This diagnostic is not a flight-qualified image.

## Acquisition-path inspection

The compiled Attitude path consumes the combined IMU queue directly, averages
the integer samples, applies scale, optional temperature compensation and board
rotation, then adds the adaptive gyro bias. The recorder's input gyro therefore
already includes that bias; it is not raw register data. Inspection of the
separate Sensors module alone does not establish this compiled path's behavior.

The current capture lacks the raw sample and simultaneous bias value needed to
separate an acquisition spike from a bias change. No specific arithmetic defect
has been established. Further instrumentation should record these quantities
without changing PID gains, filtering, or the readings delivered to control.
