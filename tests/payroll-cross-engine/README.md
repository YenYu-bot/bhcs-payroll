# Cross-engine isolated feasibility

Fixed candidate and existing seven synthetic migration cases only. Not a production or Safari/device certification.
Pinned Playwright 1.56.0 official browser downloads. Non-root runtime receives clean environment, loopback-only network namespace, no credentials, SDK or production data. Supervisor owns only descendants and enforces timeout/cleanup.

Before creating the candidate HTTP server, the same browser instance renders a constant blank probe. Fail-closed gate checks its descendant content processes and /proc sandbox evidence. No sandbox-disabling flags/environment, root browser, system sandbox changes, permission relaxation or fallback launch. A BLOCKED probe prevents all application cases. Passing the probe permits the prior seven synthetic cases in the same browser instance.

Firefox and Linux WebKit use their own default launch settings; Chromium options/CDP are not applied. Source checked at microsoft/playwright v1.56.0 server/firefox/firefox.ts, server/webkit/webkit.ts, browser_patches/firefox/preferences/playwright.cfg and browser_patches/webkit/pw_run.sh. Source review alone is not runtime evidence.
