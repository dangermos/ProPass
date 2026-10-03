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

        ProPassScenarioRunner runner;
        Light keyLight;
        Camera[] cameras;
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
            cameras = ProPassCameras.Ensure(checkoutCamera);
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

        byte[] Capture(Camera source)
        {
            var originalTarget = source.targetTexture;
            var originalActive = RenderTexture.active;
            try
            {
                source.targetTexture = captureTarget;
                source.Render();
                RenderTexture.active = captureTarget;
                capturePixels.ReadPixels(new Rect(0, 0, captureWidth, captureHeight), 0, 0);
                capturePixels.Apply(false);
                return capturePixels.EncodeToJPG(85);
            }
            finally
            {
                source.targetTexture = originalTarget;
                RenderTexture.active = originalActive;
            }
        }

        IEnumerator SendFrame()
        {
            captureBusy = true;
            // Every camera is captured at the same instant and shares one frame_id.
            // Only JPEG pixels and source-frame timing are sent to the checkout API.
            var jpegs = new byte[cameras.Length][];
            for (int i = 0; i < cameras.Length; i++) jpegs[i] = Capture(cameras[i]);
            long currentFrame = ++frameId;
            string query = "/api/frames?frame_id=" + currentFrame + "&timestamp=" +
                scenarioTime.ToString("F4", CultureInfo.InvariantCulture) + "&run_id=" + UnityWebRequest.EscapeURL(runId);
            for (int i = 0; i < cameras.Length; i++)
            {
                using (var request = new UnityWebRequest(serverUrl + query + "&camera_id=" + ProPassCameras.Ids[i], "POST"))
                {
                    request.uploadHandler = new UploadHandlerRaw(jpegs[i]);
                    request.downloadHandler = new DownloadHandlerBuffer();
                    request.SetRequestHeader("Content-Type", "image/jpeg");
                    request.timeout = 3;
                    yield return request.SendWebRequest();
                    if (request.result == UnityWebRequest.Result.Success) sentFrames++;
                    else { failedFrames++; connectionStatus = "API connection pending"; }
                }
            }
            captureBusy = false;
        }

        void OnDestroy()
        {
            runner?.Dispose();
            ProPassCameras.Release();
            if (captureTarget != null) { captureTarget.Release(); Destroy(captureTarget); }
            if (capturePixels != null) Destroy(capturePixels);
        }
    }
}
