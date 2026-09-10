# Host pending credential storage

`provisioning_bundle.py` implements a POSIX storage primitive, not a provisioning
CLI or transport. It requires an existing owner-owned mode-0700 directory outside
Git. New transaction files are exclusive, mode 0600, and never overwrite previous
bundles. Reads reject symlinks, hardlinks, non-regular files, wrong ownership or
permissions, malformed credentials, filename mismatch and record corruption.

The 192-byte record contains `LWPEND01`, a 16-byte transaction, the 136-byte LWCF
blob, and a SHA256 corruption check. This is plaintext, not encryption or a MAC.
Same-user/root attackers, filesystem backups and immutable Python RAM copies
are outside these protections. No credential contents enter exceptions or logs.

Save success requires complete writes, file fsync, exact descriptor readback,
directory fsync and successful closes. On any failure, created records remain
for explicit recovery; no success is returned and a caller must not transmit.
An ambiguously closed descriptor is never retried. OS fsync success does not
prove survival of every storage-device or power-loss failure. Load validates
bytes but does not establish a board write, activation, or permission to send.

At `218736f`, seven synthetic bundle tests passed as part of the full host suite:
235 tests ran, 226 passed, nine optional OpenAI-extra tests skipped. Failure
injection covers short writes, file/directory fsync and ambiguous directory close.
Tests also cover rotation preservation, duplicate rejection, private permissions,
Git placement rejection, aliases and malformed files. The close test exposed an
unsanitized error before the fix. These are local macOS results, not Linux or
Windows runtime evidence.

Windows provisioning explicitly fails closed until an equivalent private ACL,
handle and directory-durability backend is implemented. Existing cross-platform
AI/audit features are unchanged. Pending-bundle promotion, credential generation,
serial submission/status reconciliation and combined lifecycle testing remain.
No real credentials, external API calls or board operations were performed.

## ACL review correction

Review found that mode bits alone do not exclude macOS extended ACL grants.
At `eeb3586`, the directory descriptor, newly created file before writing, and
every loaded file also undergo ACL checks. macOS rejects any present extended
ACL and any retrieval error except the documented implementation's absent-ACL
case. Linux rejects descriptor-listed POSIX access/default ACL attributes;
other POSIX platforms are unsupported. Network filesystems with additional
server-side authorization semantics are not qualified by these local tests.

The macOS backend follows Apple's [descriptor ACL retrieval implementation](https://github.com/apple-oss-distributions/Libc/blob/main/posix1e/acl_file.c)
and [missing FILESEC_ACL property handling](https://github.com/apple-oss-distributions/Libc/blob/main/gen/filesec.c).
A real inherited-ACL test on a temporary directory reproduced the defect before
the fix and then verified rejection before creating any credential file. All
eight bundle tests passed after correction. Test ACLs contained no real secrets.
Independent review closed the macOS ACL finding without new blocking issues.
The post-fix full host suite ran 236 tests: 227 passed and nine optional
OpenAI-extra tests skipped. Linux ACL execution, file-specific ACL rejection and
ACL-query-error injection need additional coverage; no cross-platform acceptance
is inferred from this macOS run.
