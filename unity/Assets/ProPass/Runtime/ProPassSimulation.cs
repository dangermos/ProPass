using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEngine;
using UnityEngine.Networking;

namespace ProPass
{
    [Serializable] public sealed class SimulatorControl
    {
        public string scenario = "single";
        public string run_id;
        public bool paused;
    }

    public sealed class ProPassSimulation : MonoBehaviour
    {
        public Camera checkoutCamera;
        public GameObject[] productPrefabs;
        public Transform customer;
        public Transform occluder;
        public string serverUrl = "http://127.0.0.1:8000";
        public int captureWidth = 960;
        public int captureHeight = 540;
        public float captureHz = 8f;
        public string scenario = "single";
        public string runId;
        public bool paused;
        public int sentFrames;
        public int failedFrames;
        public string connectionStatus = "Waiting for local API";
        public float scenarioTime;
        public string replayDirectory = "";
        public int replayFrames;
        public int maximumReplayFrames = 260;

        ProPassScenarioRunner runner;
        Light keyLight;
        RenderTexture captureTarget;
        Texture2D capturePixels;
        long frameId;
        bool captureBusy;

        void Start()
        {
            Application.runInBackground = true;
            captureTarget = new RenderTexture(captureWidth, captureHeight, 24, RenderTextureFormat.ARGB32);
            captureTarget.antiAliasing = 1;
            capturePixels = new Texture2D(captureWidth, captureHeight, TextureFormat.RGB24, false);
            foreach (var l in FindObjectsByType<Light>(FindObjectsSortMode.None)) if (l.type == LightType.Directional) keyLight = l;
            if (occluder != null) occluder.gameObject.SetActive(false);
            ResetScenario("single", Guid.NewGuid().ToString("N"));
            StartCoroutine(PollControl());
            StartCoroutine(CaptureLoop());
        }

        public void ResetScenario(string nextScenario, string nextRun)
        {
            runner?.Dispose();
            scenario = nextScenario;
            runId = nextRun;
            scenarioTime = 0f;
            frameId = 0;
            replayFrames = 0;
            paused = false;
            // Each run gets its own seed, so messy scenarios vary between runs but replay exactly.
            var plan = ProPassScenarios.Build(nextScenario, (nextRun ?? "").GetStableHash() % 100000);
            runner = new ProPassScenarioRunner(plan, productPrefabs, checkoutCamera, keyLight, customer);
        }

        void Update()
        {
            if (paused || runner == null) return;
            scenarioTime += Time.deltaTime;
            runner.Apply(scenarioTime);
        }

        IEnumerator PollControl()
        {
            while (true)
            {
                using (var request = UnityWebRequest.Get(serverUrl + "/api/simulator/control"))
                {
                    request.timeout = 2;
                    yield return request.SendWebRequest();
                    if (request.result == UnityWebRequest.Result.Success)
                    {
                        try
                        {
                            var control = JsonUtility.FromJson<SimulatorControl>(request.downloadHandler.text);
                            if (!string.IsNullOrEmpty(control.run_id) && control.run_id != runId)
                                ResetScenario(control.scenario, control.run_id);
                            paused = control.paused;
                            connectionStatus = paused ? "Capture paused for cart review" : "Connected to learned vision API";
                        }
                        catch (Exception error) { connectionStatus = "Invalid simulator control: " + error.Message; }
                    }
                }
                yield return new WaitForSecondsRealtime(.35f);
            }
        }

        IEnumerator CaptureLoop()
        {
            while (true)
            {
                if (!paused && !captureBusy && checkoutCamera != null)
                    yield return SendFrame();
                yield return new WaitForSecondsRealtime(1f / Mathf.Max(1f, captureHz));
            }
        }

        IEnumerator SendFrame()
        {
            captureBusy = true;
            var originalTarget = checkoutCamera.targetTexture;
            var originalActive = RenderTexture.active;
            byte[] jpeg;
            try
            {
                checkoutCamera.targetTexture = captureTarget;
                checkoutCamera.Render();
                RenderTexture.active = captureTarget;
                capturePixels.ReadPixels(new Rect(0, 0, captureWidth, captureHeight), 0, 0);
                capturePixels.Apply(false);
                jpeg = capturePixels.EncodeToJPG(85);
            }
            finally
            {
                checkoutCamera.targetTexture = originalTarget;
                RenderTexture.active = originalActive;
            }
            long currentFrame = ++frameId;
            // Recording annotations are offline evaluator data. Only JPEG pixels
            // and source-frame timing are sent to the checkout API below.
            if (!string.IsNullOrEmpty(replayDirectory) && replayFrames < maximumReplayFrames)
            {
                string directory = Path.Combine(replayDirectory, scenario, runId);
                Directory.CreateDirectory(directory);
                string stem = currentFrame.ToString("D6");
                File.WriteAllBytes(Path.Combine(directory, stem + ".jpg"), jpeg);
                var truth = new List<ReplayProduct>();
                foreach (var product in runner.Products)
                    if (product != null)
                    {
                        var label = product.GetComponent<ProPassProduct>();
                        var point = checkoutCamera.WorldToViewportPoint(product.transform.position);
                        truth.Add(new ReplayProduct { sku = label.sku, physical_id = label.physicalId,
                            image_x = point.x, image_y = 1f-point.y });
                    }
                File.WriteAllText(Path.Combine(directory, stem + ".json"), JsonUtility.ToJson(new ReplayFrame {
                    frame_id = currentFrame, timestamp = scenarioTime, run_id = runId,
                    scenario = scenario, ground_truth = truth.ToArray() }));
                replayFrames++;
            }
            string url = serverUrl + "/api/frames?frame_id=" + currentFrame + "&timestamp=" +
                scenarioTime.ToString("F4", CultureInfo.InvariantCulture) + "&run_id=" + UnityWebRequest.EscapeURL(runId);
            using (var request = new UnityWebRequest(url, "POST"))
            {
                request.uploadHandler = new UploadHandlerRaw(jpeg);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "image/jpeg");
                request.timeout = 3;
                yield return request.SendWebRequest();
                if (request.result == UnityWebRequest.Result.Success) sentFrames++;
                else { failedFrames++; connectionStatus = "API connection pending"; }
            }
            captureBusy = false;
        }

        void OnDestroy()
        {
            runner?.Dispose();
            if (captureTarget != null) { captureTarget.Release(); Destroy(captureTarget); }
            if (capturePixels != null) Destroy(capturePixels);
        }

        [Serializable] class ReplayFrame
        {
            public long frame_id;
            public float timestamp;
            public string run_id, scenario;
            public ReplayProduct[] ground_truth;
        }
        [Serializable] class ReplayProduct
        {
            public string sku, physical_id;
            public float image_x, image_y;
        }
    }
}
