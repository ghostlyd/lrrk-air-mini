# Parts selection and purchase gates

Reviewed 2026-09-09. This is a source-backed inventory, not a claim that a
specific battery or replacement assembly was fitted or tested. The owner has
no battery. Owner photos confirm a printed **V1.2** marking; the source
directory `LieWingV2.6.C` also contains this same silkscreen text. See the
[photo identification record](verification/board-photo-identification-2026-09-09.md)
for observations and the remaining electrical/connector checks. USB-C has
since supported a [bounded Armed/nonzero-command bench proof](verification/armed-nonzero-motor-proof-2026-09-09.md),
but that does not remove the flight-battery requirement or resolve battery
connector, polarity, fit, mass, charge-current, or discharge-current selection.
The later [final configuration record](verification/final-flight-configuration-2026-09-10.md)
confirms the installed motor directions and normal arming/IMU configuration,
but likewise does not validate a battery or propeller SKU.

## Required versus optional

| Item | Quantity | Evidence and selection status |
| --- | --- | --- |
| Existing LiteWing controller/PCB | 1 | Printed V1.2 confirmed; candidate V2.6.C source design also prints V1.2 and visually matches; electrical equivalence remains unverified |
| Battery | 1 | Required for eventual flight; voltage class established below, exact SKU blocked on connector, polarity, dimensions, mass and charging compatibility |
| Coreless brushed motors | 4 | Published LiteWing specification says 720; inspect fitted motors before buying replacements |
| Matched propellers | 4 | Published sizes are 55 or 65 mm; match fitted motor shafts, rotation, guards and clearance; do not assume interchangeable assemblies |
| Battery retention and guards | 1 fitted set | Inspect existing kit and retain secure mounting; no exact replacement SKU verified |
| USB data cable | 1 | Existing USB connection succeeded; no additional USB programmer is implied |
| Development host | 1 | Existing Mac runs firmware build and native simulation; no onboard AI computer required for advisory assistance |
| Positioning add-ons | Optional | VL53L1X and PMW3901 are advertised options; neither is enabled in the initial OpenPilot hardware wrapper |

The [publisher's current wiki](https://circuitdigest.com/wiki/litewing/) lists
720 motors, the propeller sizes above, and optional ranging/flow sensors. It
shows a V3 board; those descriptions do not identify the owner's board revision
or prove that advertised stock-firmware features exist in this OpenPilot port.
Its MS5611 barometer entry remains marked coming soon. Do not buy a barometer
merely because the experimental simulator injects barometric data.

## Battery: established requirements and unresolved connector

The [publisher's battery guide](https://circuitdigest.com/articles/how-to-select-right-battery-for-litewing)
specifies a standard 1S LiPo: 3.7 V nominal, 4.2 V charging voltage, at least
20C discharge capability. It names a 2.0 mm Molex 51005/51006 (MX2.0) connector
and warns that polarity varies between vendors. Its shopping suggestions are
explicitly not purchased, tested or verified by the author.

In contrast, the checked-in
[`V2.6.C BOM`](../hardware/LieWingV2.6.C/production/bom.csv) identifies J2 as
`JST XH 2P 2.50mm SMD Hoz`, footprint `CONN-TH_2P-P2.50_XH-2AW`, LCSC C33132.
The V2.6.C KiCad schematic repeats that value and XH-2AW part number. This
conflict must not be resolved by assuming either connector is fitted.

Before selecting an exact battery, record:

1. Board marking and connector photograph: received; V1.2 and PCB +/- visible. Record electrical confirmation separately.
2. Connector pitch/type and independently verified polarity of the proposed pack.
3. Available mounting dimensions and allowed pack mass, including retention.
4. Pack manufacturer's continuous discharge and maximum charge-current ratings.
5. Actual board charge-current setting, or a compatible external charger.

The TP4056 part name alone does not establish the fitted charging current or
compatibility with a small pack. Do not substitute a higher-voltage multi-cell
pack, assume a LiHV charging profile, or bridge mismatched connectors. No
battery SKU, adapter, repinning operation or purchase is approved by this list.

## Software dependencies and validation

See [port and dependency inventory](PORT_AND_DEPENDENCIES.md) for ESP-IDF,
the pinned flight source and host-only AI boundary. Installed Gazebo/native
simulator dependencies and verified Python bindings are recorded in
[dependency verification](verification/gazebo-dependencies-2026-09-09.md).
The [world fidelity review](verification/litewing-world-fidelity-2026-09-09.md)
separates simulation assumptions from physical parts specifications.
