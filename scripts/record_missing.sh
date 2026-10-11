#!/bin/bash
# Records the held-out runs the interrupted recording did not finish. One Unity at a time.
cd "/home/dangermos/Home Depot Internship Project/propass"
U=~/Unity/Hub/Editor/6000.6.4f1/Editor/Unity
OUT="$PWD/artifacts/benchmark-test"
nice -n 10 ionice -c2 -n7 "$U" -batchmode -quit -projectPath unity -logFile artifacts/logs/unity-record-locked.log -executeMethod ProPass.Editor.ProPassBenchmarkRecorder.RunFromCommandLine -benchmarkOut "$OUT" -benchmarkScenarios locked -benchmarkSeedStart 13 -benchmarkSeeds 2
echo "locked exit $? $(date +%T)"
nice -n 10 ionice -c2 -n7 "$U" -batchmode -quit -projectPath unity -logFile artifacts/logs/unity-record-lumber.log -executeMethod ProPass.Editor.ProPassBenchmarkRecorder.RunFromCommandLine -benchmarkOut "$OUT" -benchmarkScenarios lumber -benchmarkSeedStart 10 -benchmarkSeeds 5
echo "lumber exit $? $(date +%T)"
