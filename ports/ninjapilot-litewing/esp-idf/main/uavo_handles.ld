/*
 * Generated UAVObjects place their handles in _uavo_handles. Keep the output
 * section writable and retain its name so GNU ld supplies the start/stop
 * symbols walked by uavobjectmanager.c. The heap must begin after the table.
 */
SECTIONS
{
  _uavo_handles :
  {
    . = ALIGN(4);
    KEEP(*(_uavo_handles))
    . = ALIGN(4);
  } > dram0_0_seg
}

_heap_start = ALIGN(ADDR(_uavo_handles) + SIZEOF(_uavo_handles), 16);
