#!/bin/bash
# One command for a whole round: label art, scene, training data, both camera model pairs,
# development recordings and their score. Stages run one at a time and each heavy one is
# throttled, so the desktop stays usable. Every stage is skipped if its output is already
# there, so a stopped round picks up where it left off.
#
#   scripts/round.sh            run everything that is missing
#   scripts/round.sh score      run from one stage on (art scene export train record score test tour)
#   tail -f artifacts/logs/round.log      watch it; the dashboard Training tab shows the same
#
# The held-out test set and the site videos are separate on purpose:
#   scripts/round.sh test       record and score fresh held-out seeds, once, after tuning is finished
#   scripts/round.sh tour       60 fps footage and the tour videos
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"; PY=.venv/bin/python; LOG=artifacts/logs/round.log; mkdir -p artifacts/logs
TRAIN=3400; VAL=500; TEST=500; SLICE=800          # training scenes, and how many one Unity launch exports
DEV_SEEDS=5; TEST_SEED_START=15                   # development seeds 0-4; held-out seeds 15-19
WORKERS=4                                         # scoring processes
SCENE_GROUPS=("single,duplicate,mixed,occlusion,remove,unknown" "hands,shopper,flatbed,edge,stacked,distractors" "bystander,hesitate,parked,locked,lumber")
FROM="${1:-art}"; STARTED=0
say() { echo "[$(date +%T)] $*" | tee -a "$LOG"; }
stage() { [ "$STARTED" = 1 ] || [ "$1" = "$FROM" ] && STARTED=1; [ "$STARTED" = 1 ]; }
light() { nice -n 10 ionice -c2 -n7 "$@"; }
headroom() {   # stop early rather than push a loaded machine over
  local free; free=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)
  say "  memory available ${free} GB, GPU $(nvidia-smi --query-gpu=memory.used,temperature.gpu --format=csv,noheader 2>/dev/null)"
  [ "$free" -ge 6 ] || { say "STOPPED: under 6 GB of memory available. Close something and rerun: scripts/round.sh $1"; exit 3; }
}
unity() { scripts/unity_run.sh "$@" >> "$LOG" 2>&1; }
record() {   # record <folder> <first seed>
  for group in "${SCENE_GROUPS[@]}"; do
    headroom record
    unity "record-$(basename "$1")" ProPass.Editor.ProPassBenchmarkRecorder.RunFromCommandLine -benchmarkOut "$ROOT/$1" \
      -benchmarkSeeds "$DEV_SEEDS" -benchmarkSeedStart "$2" -benchmarkScenarios "$group" || { say "FAILED recording $group"; exit 1; }
    say "  recorded $group: $(ls "$1"/*/*/run.json 2>/dev/null | wc -l) of 85 runs"
  done
}

if stage art; then say "1/7 label art"; $PY scripts/prepare_products.py >> "$LOG" 2>&1 || exit 1; fi
if stage scene; then say "2/7 scene"; unity build-scene ProPass.Editor.ProPassSceneBuilder.Build || { say "FAILED scene"; exit 1; }; fi

if stage export; then
  TOTAL=$((TRAIN + VAL + TEST))
  done_scenes() { $PY -c "import json;print(json.load(open('training/data/export-progress.json'))['completed'])" 2>/dev/null || echo 0; }
  say "3/7 training data: $TOTAL scenes"
  at=$(done_scenes)
  while [ "$at" -lt "$TOTAL" ]; do
    headroom export
    unity export ProPass.Editor.ProPassDatasetExporter.ExportFromCommandLine -exportOut "$ROOT/training/data" \
      -exportTrain $TRAIN -exportVal $VAL -exportTest $TEST -exportStart "$at" -exportStop $((at + SLICE)) || { say "FAILED export at $at"; exit 1; }
    at=$(done_scenes); say "  exported $at of $TOTAL"
  done
  light $PY -m training.extract_outliers >> "$LOG" 2>&1
fi

if stage train; then
  n=0
  for camera in lane overhead; do
    n=$((n + 1)); say "4/7 training the $camera camera's models ($n of 2)"; headroom train
    light $PY -m training.train detector --epochs 60 --batch 16 --imgsz 640 --device 0 --camera $camera > "artifacts/logs/train-$camera-detector.log" 2>&1 || { say "FAILED detector $camera"; exit 1; }
    light $PY -m training.train classifier --epochs 12 --head-epochs 4 --batch 32 --device cuda:0 --camera $camera > "artifacts/logs/train-$camera-classifier.log" 2>&1 || { say "FAILED classifier $camera"; exit 1; }
    say "  $camera: $($PY -c "
import json;m=json.load(open('models/manifest.json' if '$camera'=='lane' else 'models/$camera/manifest.json'))
print('detector mAP50-95 %.3f, classifier %.1f%%' % (m['detector']['test']['map50_95'], 100*m['classifier']['test']['accuracy']))")"
  done
fi

if stage record; then say "5/7 recording 85 development runs (seeds 0-$((DEV_SEEDS - 1)))"; record artifacts/benchmark 0; fi

if stage score; then
  say "6/7 scoring the development runs on $WORKERS processes"; headroom score
  light $PY -m training.benchmark --root artifacts/benchmark --label dev --output models/benchmark-dev.json --workers $WORKERS > artifacts/logs/score-dev.log 2>&1 || { say "FAILED scoring"; exit 1; }
  say "  development: $(grep -c '^PASS' artifacts/logs/score-dev.log) of 85 pass"
fi

# Only on request: looking at the held-out runs spends them.
if [ "$FROM" = test ]; then
  say "7/7 held-out seeds $TEST_SEED_START-$((TEST_SEED_START + DEV_SEEDS - 1)): record, then score once"
  record artifacts/benchmark-test "$TEST_SEED_START"; headroom test
  light $PY -m training.benchmark --root artifacts/benchmark-test --label "held-out seeds $TEST_SEED_START-$((TEST_SEED_START + DEV_SEEDS - 1))" \
    --output models/benchmark-test.json --workers $WORKERS --docs > artifacts/logs/score-test.log 2>&1 || { say "FAILED scoring held-out"; exit 1; }
  say "  held-out: $(grep -c '^PASS' artifacts/logs/score-test.log) of 85 pass"
fi

if [ "$FROM" = tour ]; then
  say "tour: 60 fps footage of seed 2, four scenes per Unity launch"
  for group in single,duplicate,mixed,occlusion remove,unknown,hands,shopper flatbed,edge,stacked,distractors bystander,hesitate,parked,locked lumber; do
    headroom tour
    unity record-video ProPass.Editor.ProPassBenchmarkRecorder.RecordVideoFromCommandLine -videoOut "$ROOT/artifacts/video60" -videoFps 60 -videoSeed 2 -benchmarkScenarios "$group" || { say "FAILED footage $group"; exit 1; }
  done
  say "tour: drawing the models' decisions over the footage"
  nice -n 19 ionice -c3 taskset -c 12-23 $PY scripts/build_tour.py > artifacts/logs/build-tour.log 2>&1 || { say "FAILED tour"; exit 1; }
fi
say "done"
