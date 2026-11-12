# Isolated payroll v3 validation (test branch only)

This directory is synthetic test material, not a release. The root application, main branch, and GitHub Pages are unchanged.

The candidate index is the reviewed v3 SHA-256 3437f75e85fc64c088ea24a7f5e5e2f7d4824d43f7ddcd299e25356b37784e67. Harness files are copied unchanged from the reviewed r3 package. The fixtures contain fictional employees only.

The workflow provisions locked official dependencies online, then runs all app/emulator/browser activity as non-root inside a fresh network namespace with only loopback. No secrets are supplied. A separate fail-closed gate checks Chromium's sandbox report and renderer protection before the harness may start. Failure to establish the namespace or sandbox blocks testing; it is not a reason to disable protections.

This workflow is push-triggered only on test/payroll-v3-isolated-20261112. It has contents:read, does not retain Git credentials, and performs no merge or deployment. Test artifacts are retained for 14 days. A green tooling check is not a payroll legal/calculation audit or production release approval.
