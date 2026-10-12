#!/bin/bash
# Renders seed 2 of every scenario at 60 fps for the site and tour videos (pictures only, about 4 GB).
# One Unity at a time, held to half the cores and 12 GB so the desktop stays usable.
# Watch it: tail -f artifacts/logs/record-video.out
cd "$(dirname "$0")/.."
SCENARIOS="${1:-}"
systemd-run --user --scope -q -p MemoryMax=12G -p MemorySwapMax=4G \
  nice -n 15 ionice -c2 -n7 taskset -c 12-23 ~/Unity/Hub/Editor/6000.6.4f1/Editor/Unity -batchmode -quit -projectPath unity \
  -logFile artifacts/logs/unity-record-video.log -executeMethod ProPass.Editor.ProPassBenchmarkRecorder.RecordVideoFromCommandLine \
  -videoOut "$PWD/artifacts/video60" -videoFps 60 -videoSeed 2 ${SCENARIOS:+-benchmarkScenarios "$SCENARIOS"}
echo "record video exit $? $(date +%T)"
