using System;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace ProPass.Editor
{
    // Builds the checkout scene for the browser into web/public/unity, so a live lane can run
    // from the dashboard without the Unity Editor. The page still needs the local API for vision.
    //   Unity -batchmode -quit -projectPath unity -buildTarget WebGL -executeMethod ProPass.Editor.ProPassWebBuild.BuildFromCommandLine
    public static class ProPassWebBuild
    {
        const string Output = "../web/public/unity";

        [MenuItem("ProPass/Build for the browser (WebGL)")]
        public static void Build()
        {
            PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Gzip;
            PlayerSettings.WebGL.decompressionFallback = true;   // plain static servers do not send Content-Encoding
            PlayerSettings.WebGL.exceptionSupport = WebGLExceptionSupport.ExplicitlyThrownExceptionsOnly;
            PlayerSettings.runInBackground = true;
            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions {
                scenes = new[] { ProPassBenchmarkRecorder.ScenePath }, locationPathName = Output,
                target = BuildTarget.WebGL, options = BuildOptions.None });
            var summary = report.summary;
            Debug.Log($"ProPass WebGL build: {summary.result}, {summary.totalSize / 1048576f:F1} MB, {summary.totalTime.TotalMinutes:F1} min, {summary.totalErrors} errors");
            if (summary.result != BuildResult.Succeeded) throw new Exception("WebGL build failed: " + summary.result);
        }

        public static void BuildFromCommandLine()
        {
            try { Build(); EditorApplication.Exit(0); }
            catch (Exception error) { Debug.LogException(error); EditorApplication.Exit(1); }
        }
    }
}
