#!/usr/bin/env bash
# Build the Chrome Web Store zip. See README.md ("Packaging for the Web Store")
# for what differs from the dev tree and why.
set -euo pipefail

cd "$(dirname "$0")"

VERSION=$(python3 -c "import json; print(json.load(open('manifest.json'))['version'])")
OUT="dist/hudson-edmspro-${VERSION}.zip"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

# Everything the extension loads at runtime, and nothing it doesn't.
rsync -a \
  --exclude 'dist' \
  --exclude '.gitignore' \
  --exclude 'README.md' \
  --exclude 'package-store.sh' \
  --exclude 'picker.js' \
  --exclude 'lib/upload.js' \
  --exclude '*.pem' \
  --exclude '*.crx' \
  ./ "$STAGE/"

# Dev-only host permissions never ship: they exist so an unpacked build can
# talk to a local Django without CORS.
python3 - "$STAGE/manifest.json" <<'PY'
import json, sys

path = sys.argv[1]
with open(path) as f:
    manifest = json.load(f)

manifest["host_permissions"] = [
    h for h in manifest["host_permissions"] if not h.startswith("http://")
]

with open(path, "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
PY

mkdir -p dist
rm -f "$OUT"
python3 - "$STAGE" "$OUT" <<'PY'
import os, sys, zipfile

stage, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, _dirs, files in os.walk(stage):
        for name in sorted(files):
            path = os.path.join(root, name)
            zf.write(path, os.path.relpath(path, stage))
    for info in zf.infolist():
        print(f"  {info.file_size:>9}  {info.filename}")

print(f"Wrote {out}")
PY
