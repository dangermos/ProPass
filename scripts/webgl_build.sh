#!/bin/bash
# WebGL build, held to 12 of 24 cores and 12 GB so the desktop stays usable. If it needs more, it is killed, not the machine.
cd "/home/dangermos/Home Depot Internship Project/propass"
systemd-run --user --scope -q -p MemoryMax=12G -p MemorySwapMax=4G \
  nice -n 19 ionice -c3 taskset -c 12-23 ~/Unity/Hub/Editor/6000.6.4f1/Editor/Unity -batchmode -quit -projectPath unity -buildTarget WebGL \
  -logFile artifacts/logs/unity-webgl.log -executeMethod ProPass.Editor.ProPassWebBuild.BuildFromCommandLine
echo "webgl build exit $? $(date +%T)"
