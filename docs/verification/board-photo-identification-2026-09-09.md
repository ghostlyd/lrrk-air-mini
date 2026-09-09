# Owner board: photographic identification

Reviewed 2026-09-09 from four owner-supplied photos. These are visual
observations, not electrical measurements or proof of a functioning port.
Original photos remain private attachments; they are not committed here.

## Visible observations

| Observation | Photo evidence | Limit |
| --- | --- | --- |
| Board marking `Lite Wing V 1.2`, SEMICONLAB branding | Photos 3 and 4 | A printed board marking, not an installed firmware version |
| ESP32-S3-WROOM-1 module | Photos 3 and 4 | Marking is readable; no flash/RAM capacity inferred |
| InvenSense MPU-6050 | Photos 3 and 4 | Package identification only; no WHO_AM_I or live sample checked |
| CH340K USB bridge | Photos 3 and 4 | Package marking; not a new serial/transport test |
| Two-contact battery receptacle beside USB-C | Photos 2–4 | No ruler or caliper reference; exact pitch, manufacturer and mating part are not confirmed |
| Battery PCB `+` on image-left, `-` on image-right | Photo 4, component side facing camera, ESP antenna up and USB-C down | Silkscreen observation only; independently verify the board and any pack electrically before connection |
| PMW3901 / VL53L1X labeled connection areas unpopulated | Photo 1, underside | No positioning module visible at these connections; labels alone do not mean sensors are fitted |
| Propellers fitted and USB cable connected | All photos | No motor motion or safe-output state inferred from a still image |

## Source-directory name versus printed revision

The checked-in file
`hardware/LieWingV2.6.C/LieWingV2.6.C.kicad_pcb` contains
`(gr_text "V 1.2" ...)` on `F.SilkS`. Its accompanying `LieWingV2.6.C Front.png`
also shows that marking. The module, switches, USB, connector, headers and
indicator placement closely match the owner photos after rotation.

Therefore, the V1.2 photo marking does **not** by itself contradict using
`LieWingV2.6.C` as the candidate source design. These are different naming
layers. Visual correspondence is not proof that every component, net, fitted
connector, or motor pin assignment matches the source; those checks remain
open before hardware activation.

## Battery selection consequence

The photos satisfy the request for a board marking and connector/polarity
view. They do not resolve the documented 2.50 mm XH BOM versus 2.0 mm
MX/Molex publisher-guide discrepancy. Do not select an exact mating part from
appearance alone. A physical pitch measurement or supplier confirmation for
this fitted connector is still required, together with pack polarity, mass,
fit, discharge capability and charging-current compatibility.

See [parts selection](../PARTS_SELECTION.md). No battery SKU is marked
verified, and no repinning, purchase, firmware flashing or motor test was
performed. Disconnect USB before handling/removing propellers; hardware
bench work remains propeller-off and separately gated.
