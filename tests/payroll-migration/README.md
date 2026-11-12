# Synthetic backup and migration acceptance, batch 1

This runner supplements the already-passed native IDB and official SDK suites. It does not re-test payroll arithmetic or imply production readiness.

## Run in the authorized isolated CI only

```
python3 -I migration_runner.py --candidate-root ../candidate --harness-dir ../harness --output /new/output/path
```

Use the existing sandbox gate, clean environment, no-uplink network namespace and outer `supervise.py` timeout. It refuses root and always requests Chromium sandbox. The candidate SHA is fixed. No Firebase SDK or emulator is loaded; every context uses the existing default-deny browser guard with SDK substitution disabled. Inputs are synthetic. Do not run on a machine with production payroll sessions.

## Cases

- M01: explicit v2→v3 field conversion using independently written expected values: employee fields/defaults, removal of obsolete fields, day-to-hour conversions, rest-hour chunks, annual leave date, bonus/deduction/override mapping. It verifies implemented conversion, not the legal or business desirability of its defaults. It does not preserve fields that v2 intentionally does not migrate.
- M02: v3 fixture's complete employee/month data, including confirmed historical snapshot, survives first initialization and reload without canonical writes.
- M03: cancelled initialization, wrong backup password, malformed JSON and unknown version leave canonical root absent.
- M04: two initially empty pages both reach the initialization gate before release; one succeeds, one fails, root revision is 1 and contains only the winner. This is a controlled app-level bootstrap race, not proof of overlapping native IDB transactions.
- M05: cancellation, wrong password, malformed JSON and unknown version during existing-data import preserve exact canonical envelope and RAM. Wrong-password value is supplied at the app's `askPass` boundary; file input, encryption and persistence are real.
- M06: legacy localStorage is retained; another same-origin page's legacy write warns but cannot replace canonical root or reloaded state. This is not a test of a legacy client's cloud write.
- M07: 390×844 desktop Chromium viewport: password field is in viewport, independently generated encrypted backup imports and unlocks, actual encrypted download decrypts, and that download imports into another fresh context without changing historical snapshots. Not a mobile device or other browser engine claim.

No native browser has been run in the authoring environment because sandbox launch was previously denied. Completed local validation is Python compilation/static checks only. CI results must be read before claiming PASS.

Still excluded: real quota exhaustion, browser/OS crashes and power loss, Firefox/WebKit/Android devices, production login/rules, genuine user backup migration, browser-upgrade blocked database scenarios, old clients' remote writes, and larger-scale historical data.
