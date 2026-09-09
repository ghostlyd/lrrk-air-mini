/*
 * Generated UAVObjects place their handles in _uavo_handles. Keep the output
 * section writable and retain its name so GNU ld supplies the start/stop
 * symbols walked by uavobjectmanager.c. The heap must begin after the table.
 */
/* Weak UAVObjSave/Load/Delete aliases otherwise satisfy archive references.
 * Force extraction of the pinned real persistence implementation. */
EXTERN(uavobject_persistence_linked)
EXTERN(litewing_checked_delete_linked)

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
