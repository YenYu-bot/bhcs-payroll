# Leave settlement isolated validation candidate

Test branch only. Root index.html, main, GitHub Pages and production data are unchanged.

Candidate SHA256: ff5399e07c7e023de6db13c3983acec5d991d82de54e25782109851a7ea64782.

Includes leave/resignation boundary fixes, pre-six-month advances, actual scheduled full-shift checks, same-day split leave and individual source acknowledgement; deferred leave uses individually verified original-period wage bases. Missing bases block confirmation/output. Confirmed snapshots are not recalculated. This is not a production release or full legal sign-off.

Only fictional employee data. All browser/application/emulator runs remain non-root, Chromium sandbox enabled, in a fresh loopback-only network namespace and clean environment without production credentials. Existing sandbox gate, firewall checks, simulator rules, dependency locks and negative controls remain in place. No merge or deployment step.

The existing full isolated regression, 30 phase1 numeric checks, 30 leave checks, 23 deferred-basis checks, 36 independent leave checks and 21 independent deferred checks are rerun against this exact candidate. Additional native UI tests cover source acknowledgements, original-wage input, local persistence and incomplete-settlement print/output blocking. VM assertions are not native-browser results.
