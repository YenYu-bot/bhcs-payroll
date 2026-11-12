#!/usr/bin/env bash
# Pre-provision the LOCKED dependencies for the BSDK suite. Run as a non-root user, ONLY in an environment whose
# network policy allows the official registries (registry.npmjs.org for npm; the Firebase CLI's own emulator download
# location for the Firestore emulator jar). Not executed in this validation round: the network was disabled.
# No credentials are used: GOOGLE_APPLICATION_CREDENTIALS / FIREBASE_TOKEN are emptied, config/home are isolated.
set -euo pipefail
[ $# -ge 1 ] || { echo "usage: provision.sh <candidate-root> [--check-paths]"; exit 2; }
# Normalize to an absolute, symlink-resolved path BEFORE any cd, so a relative argument keeps its meaning.
CAND="$(cd "$1" && pwd -P)" || { echo "candidate-root not found: $1"; exit 2; }
IT="$CAND/tests/isolated-integration"
[ "$(id -u)" != 0 ] || { echo "refusing root"; exit 3; }
LOCK_SHA=e792ee4171a006155b5b8f7d8597c238e7a650f481f231e73718a99a8c59d246
echo "$LOCK_SHA  $IT/package-lock.json" | sha256sum -c -
if [ "${2:-}" = "--check-paths" ]; then echo "CAND=$CAND"; echo "IT=$IT"; exit 0; fi   # no network, no install
cd "$IT"
export GOOGLE_APPLICATION_CREDENTIALS= FIREBASE_TOKEN= FIREBASE_CLI_DISABLE_MOTD=1
export XDG_CONFIG_HOME="$IT/.provision-config" HOME="$IT/.provision-home" FIREBASE_EMULATORS_PATH="$IT/emulator-cache"
mkdir -p "$XDG_CONFIG_HOME" "$HOME" "$FIREBASE_EMULATORS_PATH"
# npm ci installs exactly the lock file and verifies every tarball's sha512 "integrity"; --ignore-scripts: no install hooks.
npm ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org/
# firebase-tools downloads the emulator jar and checks it against its built-in expectedChecksum (md5).
./node_modules/.bin/firebase setup:emulators:firestore --project demo-bhcs-payroll-isolated
node - <<'EOF' > deps-provenance.json
const fs = require('fs'), c = require('crypto'), lock = JSON.parse(fs.readFileSync('package-lock.json'));
const h = (f, a = 'sha256') => c.createHash(a).update(fs.readFileSync(f)).digest('hex');
const pick = n => { const e = lock.packages['node_modules/' + n] || {}; return {version: e.version, resolved: e.resolved, integrity: e.integrity,
  installedVersion: JSON.parse(fs.readFileSync(`node_modules/${n}/package.json`)).version}; };
const jar = 'emulator-cache/cloud-firestore-emulator-v1.19.8.jar';
console.log(JSON.stringify({recordedAt: new Date().toISOString(), node: process.version, packageLockSha256: h('package-lock.json'),
  packages: {'firebase': pick('firebase'), 'firebase-tools': pick('firebase-tools'), '@firebase/rules-unit-testing': pick('@firebase/rules-unit-testing')},
  sdkBrowserFiles: Object.fromEntries(['firebase-app.js', 'firebase-auth.js', 'firebase-firestore.js'].map(f => [f, h('node_modules/firebase/' + f)])),
  firestoreEmulatorJar: {path: jar, sha256: h(jar), md5: h(jar, 'md5')}}, null, 1));
EOF
cat deps-provenance.json
echo "provisioned; now run: python3 supervise.py --out <dir> --timeout 2700 -- python3 bsdk_runner.py --candidate-root $CAND --output <new-dir>"
