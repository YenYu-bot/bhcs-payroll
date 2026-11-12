# Calculation phase 1 isolated acceptance candidate

Test branch only. Root index.html, main, GitHub Pages and production data are unchanged.

Candidate SHA256: 7fee7b0d9296a0b1f56d12d2007c34a1c740cd70f48bc7c64d5a7342e560b42e.
Changes: monthly weekday automatic OT; same-day tier aggregation; hourly tardiness does not consume annual leave; exceptional offday >8 hours at 2x; input-sensitive reviews and individual duplicate-source acknowledgement. Confirmed snapshots remain unchanged.

Tests use fictional data. Pinned official dependencies are provisioned before execution. All app, native Chromium and Firebase emulator execution occurs non-root with sandbox enabled in a fresh loopback-only network namespace and clean environment, no production credentials. Workflow has read-only contents permission and no deployment or merge step.

VM tests are not native-browser results. Tests do not constitute full legal sign-off or authorization to release.
