# Source and license boundary

This adapter does not relicense the NinjaPilot or OpenPilot source trees. The
upstream repositories remain external, pinned inputs and retain their own
copyright and license notices. Reference patches are fetched from the pinned
OpenPilotESP32 commit and are not silently presented as original LiteWing
code.

Repository-owned files in this directory are licensed under the repository's
top-level license unless a file states otherwise. Before redistributing an
assembled upstream checkout, review the exact license notices carried by the
NinjaPilot tree, the OpenPilotESP32 tree, and any vendored library included by
their patches.

`target/pios_litewing_flashfs_nvs.c` is a GPL-3.0-or-later adaptation of the
NinjaPilot-authored `pios/esp32/pios_flashfs_nvs.c` from the pinned
OpenPilotESP32-WROOM-32E revision `7233c97f844c0377930bcdf22998e289638b64c6`.
It retains the original attribution and license notice. LiteWing changes
preserve incompatible storage rather than erasing it during initialization
or object loading. This file is not relicensed under a different project license.

The new `target/litewing_settings_recovery.c`,
`target/include/litewing_settings_recovery.h`,
`target/include/pios_litewing_flashfs.h`, and
`target/litewing_uavobject_delete.c` and `target/pios_litewing_gcsrcvr.c`
are explicitly GPL-3.0-or-later, as their
SPDX notices state. This does not change the upstream hardware license or
relicense other existing files. Assembled firmware distribution still requires
an inventory of the complete linked code and its source/notice obligations;
this local bench build is not a public binary release.

`target/include/pios_litewing_gcsrcvr.h` is also GPL-3.0-or-later.
`prepare_uavtalk.py` produces target-only copies of the pinned NinjaPilot
UAVTalk C source/private header in the build directory. Those generated files
retain their original OpenPilot GPL notices; source hashes and exact replacement
anchors reject unreviewed inputs. The adaptation adds a local packet-completion
timestamp and passes it to the target receiver. It does not relicense UAVTalk
or edit the external checkout.

`target/include/litewing_thrust_control.h` is GPL-3.0-or-later.
`prepare_control.py` generates hash-checked copies of the pinned Receiver and
Actuator translation units, retaining their OpenPilot GPL notices. They use a
checked byte read followed by validated enum conversion and fault handling.
The originals in the external checkout are not modified.

The KiCad and BOM evidence under `hardware/LieWingV2.6.C/` remains upstream
hardware attribution. This directory records the evidence used for the target
contract; it does not certify a physical board revision or fitted motor SKU.
