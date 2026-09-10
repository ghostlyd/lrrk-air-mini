# Stored credential copy, separate from activation

At `b466b90`, a matching finished/verified firmware status can produce a private
`.stored` copy of the transaction's pending bundle. Pending and older bundles
remain untouched. The copy uses the same validated binary record, ownership,
ACL, exclusive-create, exact-readback and file/directory-sync checks. Its suffix
is local workflow state, not a signed receipt or an active-network selector.

Repeated recording validates and syncs an already matching copy without writing
it again. A corrupt, aliased, permissive or different existing copy is rejected,
not repaired or overwritten. Unknown outcomes, mismatched IDs, queue ACKs and
verified storage with incomplete cleanup cannot promote a bundle.

The transaction layer retains its parsed status for a verified outcome. The
operator CLI closes serial successfully before recording the stored copy, and
returns success only after local recording also succeeds. Open/close/storage
failures preserve pending records and return unresolved without private error
details. Reconciliation never retransmits credentials.

Tests cover private/idempotent copies, pending/old preservation, corrupt-copy
rejection, sync failure, mismatched or uncertain statuses, and CLI open/close
failures. Two CLI assertions failed before wiring promotion. The full host suite
ran 259 tests on macOS: 250 passed and nine optional OpenAI-extra tests skipped.

No board was opened, reset, flashed, armed or commanded. Temporary test entropy
was never provisioned. A `.stored` file does not establish activation, reboot,
authenticated Wi-Fi connectivity or flight readiness. Those remain separate
verification steps; the module creates no `.active` file and changes no radio.

Independent review accepted the implementation. A pathname can survive failed
sync; future consumers must not infer successful promotion from existence alone.
Follow-up tests reject a valid but different existing copy and public permissions
without repair, and check directory-sync failure on repeat promotion.
