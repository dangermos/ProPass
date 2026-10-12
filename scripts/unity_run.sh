#!/bin/bash
# Runs one Unity editor method headless, held to half the cores and 12 GB so the desktop stays usable.
#   scripts/unity_run.sh <log name> <Namespace.Class.Method> [extra Unity arguments...]
cd "$(dirname "$0")/.."
NAME="$1"; METHOD="$2"; shift 2
mkdir -p artifacts/logs
systemd-run --user --scope -q -p MemoryMax=12G -p MemorySwapMax=4G \
  nice -n 15 ionice -c2 -n7 taskset -c 12-23 ~/Unity/Hub/Editor/6000.6.4f1/Editor/Unity -batchmode -quit -projectPath unity \
  -logFile "artifacts/logs/unity-$NAME.log" -executeMethod "$METHOD" "$@"
CODE=$?
git checkout -q -- unity/Assets/Settings unity/ProjectSettings/GraphicsSettings.asset 2>/dev/null
echo "$NAME exit $CODE $(date +%T)"
exit $CODE
