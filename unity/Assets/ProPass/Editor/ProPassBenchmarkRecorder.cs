using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace ProPass.Editor
{
    // Renders every scenario x seed offline at a fixed frame rate, without Play mode or the API.
    // Each frame gets the exact JPEG the live camera would send plus a separate ground-truth JSON
    // that only the benchmark scorer reads.
    //
    //   Unity -batchmode -quit -projectPath unity -executeMethod ProPass.Editor.ProPassBenchmarkRecorder.RunFromCommandLine
    //         -benchmarkOut /abs/path/artifacts/benchmark -benchmarkSeeds 4 [-benchmarkScenarios hands,shopper]
    public static class ProPassBenchmarkRecorder
    {
        public const string ScenePath = "Assets/ProPass/Scenes/Checkout.unity";
        public const float FrameRate = 8f;

        public static void RunFromCommandLine()
        {
            var args = Environment.GetCommandLineArgs();
            string Arg(string name, string fallback)
            {
                int i = Array.IndexOf(args, name);
                return i >= 0 && i + 1 < args.Length ? args[i + 1] : fallback;
            }
            string output = Arg("-benchmarkOut", null) ?? throw new ArgumentException("-benchmarkOut is required");
            int seeds = int.Parse(Arg("-benchmarkSeeds", "4"), CultureInfo.InvariantCulture);
            var scenarios = Arg("-benchmarkScenarios", null)?.Split(',') ?? ProPassScenarios.All.ToArray();
            try { Record(output, seeds, scenarios); EditorApplication.Exit(0); }
            catch (Exception error) { Debug.LogException(error); EditorApplication.Exit(1); }
        }

        [MenuItem("ProPass/Record benchmark suite")]
        public static void RecordFromMenu()
        {
            string output = EditorUtility.SaveFolderPanel("Benchmark output (propass/artifacts/benchmark)", "", "benchmark");
            if (!string.IsNullOrEmpty(output)) Record(output, 4, ProPassScenarios.All.ToArray());
        }

        // For the Unity CLI's `eval`, which times out on long main-thread calls: returns at once,
        // records on the next editor tick and logs "ProPass benchmark complete" when done.
        public static string RecordDeferred(string output, int seeds, string scenarioList = null)
        {
            var scenarios = string.IsNullOrEmpty(scenarioList) ? ProPassScenarios.All.ToArray() : scenarioList.Split(',');
            EditorApplication.delayCall += () => Record(output, seeds, scenarios);
            return "scheduled";
        }

        public static void Record(string output, int seeds, IEnumerable<string> scenarios)
        {
            if (EditorApplication.isPlaying) throw new InvalidOperationException("Stop Play mode before recording the benchmark.");
            if (UnityEngine.SceneManagement.SceneManager.GetActiveScene().path != ScenePath)
            {
                if (!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
                    throw new OperationCanceledException("Recording cancelled to keep unsaved scene changes.");
                EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            }
            var simulation = UnityEngine.Object.FindFirstObjectByType<ProPassSimulation>() ?? throw new InvalidOperationException("Checkout scene has no ProPassSimulation");
            var camera = simulation.checkoutCamera;
            var light = UnityEngine.Object.FindObjectsByType<Light>(FindObjectsSortMode.None).FirstOrDefault(l => l.type == LightType.Directional);
            if (simulation.occluder != null) simulation.occluder.gameObject.SetActive(false);
            int width = simulation.captureWidth, height = simulation.captureHeight;
            var target = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32) { antiAliasing = 1 };
            var pixels = new Texture2D(width, height, TextureFormat.RGB24, false);
            var customerStart = simulation.customer != null ? simulation.customer.position : Vector3.zero;
            int knownProducts = simulation.productPrefabs.Length - 1;
            int runs = 0, frames = 0;
            try
            {
                foreach (var scenario in scenarios)
                for (int seed = 0; seed < seeds; seed++)
                {
                    var plan = ProPassScenarios.Build(scenario, seed);
                    string runId = $"{scenario}-seed{seed:D2}";
                    string directory = Path.Combine(output, scenario, $"seed_{seed:D2}");
                    if (Directory.Exists(directory)) Directory.Delete(directory, true);
                    Directory.CreateDirectory(directory);
                    var runner = new ProPassScenarioRunner(plan, simulation.productPrefabs, camera, light, simulation.customer);
                    try
                    {
                        long frameId = 0;
                        for (float t = 0f; t <= plan.duration + 1e-4f; t += 1f / FrameRate)
                        {
                            runner.Apply(t);
                            Render(camera, target, pixels, width, height);
                            string stem = (++frameId).ToString("D6");
                            File.WriteAllBytes(Path.Combine(directory, stem + ".jpg"), pixels.EncodeToJPG(plan.jpegQuality));
                            var truth = new List<TruthProduct>();
                            for (int i = 0; i < runner.Products.Count; i++)
                            {
                                var product = runner.Products[i];
                                var label = product.GetComponent<ProPassProduct>();
                                var world = product.transform.position;
                                var box = ProjectBounds(camera, product, width, height);
                                var center = camera.WorldToViewportPoint(world);
                                truth.Add(new TruthProduct { sku = label.sku, physical_id = label.physicalId, actor = runner.ProductActorIndices[i],
                                    image_x = center.x, image_y = 1f - center.y, bbox = box,
                                    world_x = world.x, world_z = world.z, in_lane = Mathf.Abs(world.x) <= ScenarioPlan.LaneHalfWidth });
                            }
                            File.WriteAllText(Path.Combine(directory, stem + ".json"), JsonUtility.ToJson(new TruthFrame {
                                frame_id = frameId, timestamp = (float)Math.Round(t, 4), run_id = runId, scenario = scenario, ground_truth = truth.ToArray() }));
                            frames++;
                        }
                        var expected = plan.ExpectedProductCounts(knownProducts, out bool review);
                        File.WriteAllText(Path.Combine(directory, "run.json"), JsonUtility.ToJson(new RunInfo {
                            run_id = runId, scenario = scenario, seed = seed, description = plan.description,
                            duration = plan.duration, frames = (int)frameId, frame_rate = FrameRate,
                            light_intensity = plan.lightIntensity, camera_shake = plan.cameraShake, jpeg_quality = plan.jpegQuality,
                            expected_review = review,
                            expected_cart = expected.Select(kv => new CartLine { sku = simulation.productPrefabs[kv.Key].GetComponent<ProPassProduct>().sku, quantity = kv.Value }).ToArray()
                        }, true));
                    }
                    finally { runner.Dispose(); }
                    runs++;
                    Debug.Log($"ProPass benchmark: recorded {runId} ({plan.description})");
                }
            }
            finally
            {
                if (simulation.customer != null) simulation.customer.position = customerStart;
                target.Release(); UnityEngine.Object.DestroyImmediate(target); UnityEngine.Object.DestroyImmediate(pixels);
            }
            Debug.Log($"ProPass benchmark complete: {runs} runs, {frames} frames -> {output}");
        }

        static void Render(Camera camera, RenderTexture target, Texture2D pixels, int width, int height)
        {
            var originalTarget = camera.targetTexture; var originalActive = RenderTexture.active;
            try
            {
                camera.targetTexture = target; camera.Render();
                RenderTexture.active = target; pixels.ReadPixels(new Rect(0, 0, width, height), 0, 0); pixels.Apply(false);
            }
            finally { camera.targetTexture = originalTarget; RenderTexture.active = originalActive; }
        }

        // Projected (amodal) box of the whole package, in top-left pixel coordinates. It ignores
        // occlusion on purpose: the scorer uses it only to match detections to physical identities.
        static float[] ProjectBounds(Camera camera, GameObject product, int width, int height)
        {
            var renderers = product.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0) return new float[0];
            var bounds = renderers[0].bounds;
            foreach (var r in renderers) bounds.Encapsulate(r.bounds);
            float x0 = float.MaxValue, y0 = float.MaxValue, x1 = float.MinValue, y1 = float.MinValue;
            for (int i = 0; i < 8; i++)
            {
                var corner = new Vector3((i & 1) == 0 ? bounds.min.x : bounds.max.x, (i & 2) == 0 ? bounds.min.y : bounds.max.y, (i & 4) == 0 ? bounds.min.z : bounds.max.z);
                var v = camera.WorldToViewportPoint(corner);
                if (v.z <= 0) return new float[0];
                x0 = Mathf.Min(x0, v.x * width); x1 = Mathf.Max(x1, v.x * width);
                y0 = Mathf.Min(y0, (1f - v.y) * height); y1 = Mathf.Max(y1, (1f - v.y) * height);
            }
            if (x1 < 0 || y1 < 0 || x0 > width || y0 > height) return new float[0];
            return new[] { Mathf.Max(0, x0), Mathf.Max(0, y0), Mathf.Min(width, x1), Mathf.Min(height, y1) };
        }

        [Serializable] class TruthProduct { public string sku, physical_id; public int actor; public float image_x, image_y, world_x, world_z; public float[] bbox; public bool in_lane; }
        [Serializable] class TruthFrame { public long frame_id; public float timestamp; public string run_id, scenario; public TruthProduct[] ground_truth; }
        [Serializable] class CartLine { public string sku; public int quantity; }
        [Serializable] class RunInfo
        {
            public string run_id, scenario, description; public int seed, frames, jpeg_quality;
            public float duration, frame_rate, light_intensity, camera_shake;
            public bool expected_review; public CartLine[] expected_cart;
        }
    }
}
