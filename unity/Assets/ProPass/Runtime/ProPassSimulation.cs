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

        readonly List<GameObject> products = new List<GameObject>();
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
            ResetScenario("single", Guid.NewGuid().ToString("N"));
            StartCoroutine(PollControl());
            StartCoroutine(CaptureLoop());
        }

        public void ResetScenario(string nextScenario, string nextRun)
        {
            foreach (var product in products) if (product != null) Destroy(product);
            products.Clear();
            scenario = nextScenario;
            runId = nextRun;
            scenarioTime = 0f;
            frameId = 0;
            replayFrames = 0;
            paused = false;
            if (nextScenario == "duplicate") { Spawn(0, -.48f); Spawn(0, .48f); }
            else if (nextScenario == "mixed") { Spawn(0, -.8f); Spawn(2, 0f); Spawn(4, .8f); }
            else if (nextScenario == "unknown") Spawn(5, 0f);
            else Spawn(nextScenario == "remove" ? 1 : 0, 0f);
            UpdateObjects();
        }

        void Spawn(int index, float x)
        {
            if (index >= productPrefabs.Length || productPrefabs[index] == null) return;
            var product = Instantiate(productPrefabs[index]);
            product.name = "Purchased merchandise";
            product.GetComponent<ProPassProduct>().AssignInstance();
            product.transform.position = new Vector3(x, .9f, -3.4f);
            product.transform.rotation = Quaternion.Euler(0f, index == 2 ? 8f : -8f, 0f);
            products.Add(product);
        }

        void Update()
        {
            if (paused) return;
            scenarioTime += Time.deltaTime;
            UpdateObjects();
        }

        void UpdateObjects()
        {
            float progress = Mathf.Clamp01((scenarioTime - 1.5f) / 12f);
            float z = Mathf.Lerp(-3.4f, 3.8f, progress);
            if (scenario == "remove" && scenarioTime > 16f)
                z = Mathf.Lerp(3.8f, -3.4f, Mathf.Clamp01((scenarioTime - 16f) / 12f));
            foreach (var product in products)
                if (product != null) product.transform.position = new Vector3(product.transform.position.x, .9f, z);
            if (customer != null) customer.position = new Vector3(0, 0, z + .65f);
            if (occluder != null)
            {
                bool hidden = scenario == "occlusion" && scenarioTime > 7f && scenarioTime < 7.6f;
                occluder.gameObject.SetActive(hidden);
                occluder.position = new Vector3(0, 1.05f, z - .25f);
            }
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
                foreach (var product in products)
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
