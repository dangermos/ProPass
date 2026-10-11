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
        public ProPassCharacterSet characters;   // optional animated people; capsules are used when unset
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
        long frameId;
        bool captureBusy;
        // 1 in the Editor. In the browser, capturing and encoding three cameras is slower than captureHz,
        // so the scene slows down until the vision system still receives one frame every 1/captureHz of scene time.
        float playbackSpeed = 1f;

        void Start()
        {
            Application.runInBackground = true;
#if UNITY_WEBGL && !UNITY_EDITOR
            // In the browser the API is reached through the page's own origin (the dashboard proxies /api).
            serverUrl = new Uri(Application.absoluteURL).GetLeftPart(UriPartial.Authority);
#endif
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
            runner = new ProPassScenarioRunner(plan, productPrefabs, checkoutCamera, keyLight, customer, characters);
        }

        void Update()
        {
            if (paused || runner == null) return;
#if UNITY_WEBGL && !UNITY_EDITOR
            // deltaTime is capped when a capture stalls the page; the real elapsed time keeps scene time in step with the frames sent.
            scenarioTime += Time.unscaledDeltaTime * playbackSpeed;
#else
            scenarioTime += Time.deltaTime;
#endif
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
                float started = Time.realtimeSinceStartup;
                if (!paused && !captureBusy && checkoutCamera != null)
                    yield return SendFrame();
                float interval = 1f / Mathf.Max(1f, captureHz);
#if UNITY_WEBGL && !UNITY_EDITOR
                float took = Time.realtimeSinceStartup - started;
                playbackSpeed = Mathf.Lerp(playbackSpeed, Mathf.Clamp(interval / Mathf.Max(took, interval), .02f, 1f), .5f);
                if (took < interval) yield return new WaitForSecondsRealtime(interval - took);
#else
                yield return new WaitForSecondsRealtime(interval);
#endif
            }
        }

        IEnumerator SendFrame()
        {
            captureBusy = true;
            // Every camera is captured at the same instant and shares one frame_id.
            // Only JPEG pixels and source-frame timing are sent to the checkout API.
            var jpegs = new byte[cameras.Length][];
            for (int i = 0; i < cameras.Length; i++) jpegs[i] = ProPassCameras.Render(cameras[i], i).EncodeToJPG(i == 2 ? 90 : 85);
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
        }
    }
}
