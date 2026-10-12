#!/usr/bin/env bash
# Downloads one recorded run of every scenario (seed 2, three cameras, about 500 MB) into
# artifacts/benchmark, so the dashboard can play any scene through the models without Unity.
# Needs the GitHub CLI signed in to an account that can read the repository.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
TAG="${1:-recordings-carts-seed02}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
gh release download "$TAG" --repo dangermos/ProPass --dir "$TMP"
mkdir -p artifacts/benchmark
unzip -q -n "$TMP/replay-recordings.zip" -d artifacts/benchmark
echo "Recorded runs: $(ls -d artifacts/benchmark/*/seed_02 | wc -l) scenarios in artifacts/benchmark"
