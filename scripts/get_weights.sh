#!/usr/bin/env bash
# Downloads the trained cart-round weights (both camera pairs, 42 MB) from the GitHub release
# into models/. Needs the GitHub CLI signed in to an account that can read the repository.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
TAG="${1:-weights-v8-fictional}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
gh release download "$TAG" --repo dangermos/ProPass --dir "$TMP"
mkdir -p models/overhead
mv "$TMP/lane-detector.pt" models/detector.pt
mv "$TMP/lane-classifier.pt" models/classifier.pt
mv "$TMP/overhead-detector.pt" models/overhead/detector.pt
mv "$TMP/overhead-classifier.pt" models/overhead/classifier.pt
(cd models && sha256sum detector.pt classifier.pt overhead/detector.pt overhead/classifier.pt)
echo "Weights are in models/. They should match the sha256 values in models/manifest.json and models/overhead/manifest.json."
