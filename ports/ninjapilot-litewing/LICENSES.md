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

The KiCad and BOM evidence under `hardware/LieWingV2.6.C/` remains upstream
hardware attribution. This directory records the evidence used for the target
contract; it does not certify a physical board revision or fitted motor SKU.
