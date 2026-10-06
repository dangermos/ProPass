using System.Collections.Generic;
using UnityEngine;

namespace ProPass
{
    // The lane has three cameras, captured together for every frame. Ids match vision/cameras.json.
    //   lane      oblique tracking camera, saved in the scene
    //   overhead  looks straight down from the ceiling, for tracking through occlusion
    //   scan      a wide, high-resolution strip from a bar over the lane entrance, aimed at the
    //             box faces as they pass, so printed barcodes are large enough to decode
    // The overhead and scan cameras are created on demand, so the scene asset stays unchanged.
    public static class ProPassCameras
    {
        public static readonly string[] Ids = { "lane", "overhead", "scan" };
        public static readonly Vector2Int[] Sizes = { new Vector2Int(960, 540), new Vector2Int(960, 540), new Vector2Int(3840, 1080) };
        public const string OverheadName = "Overhead Camera";
        public const string ScanName = "Scan Camera";
        // Products are carried near this height; calibration maps image points onto this plane.
        public const float CarryPlaneY = .9f;

        static readonly Dictionary<Vector2Int, RenderTexture> targets = new Dictionary<Vector2Int, RenderTexture>();
        static readonly Dictionary<Vector2Int, Texture2D> buffers = new Dictionary<Vector2Int, Texture2D>();

        public static Camera[] Ensure(Camera lane)
        {
            var overhead = Find(OverheadName, lane);
            if (overhead.fieldOfView != 50f)
            {
                // Image right is +z (the direction of travel), so the long image side spans the lane.
                overhead.transform.SetPositionAndRotation(new Vector3(0f, 7.55f, 0f), Quaternion.LookRotation(Vector3.down, Vector3.left));
                overhead.fieldOfView = 50f;
            }
            var scan = Find(ScanName, lane);
            if (scan.fieldOfView != 18.9f)
            {
                // About 1,200 pixels per meter where boxes pass, 2.5-3 m ahead of the bar.
                scan.transform.position = new Vector3(0f, 2.4f, -1.8f);
                scan.transform.LookAt(new Vector3(0f, .95f, .6f));
                scan.fieldOfView = 18.9f;
            }
            var cameras = new[] { lane, overhead, scan };
            // Projections (calibration, ground truth) must use the capture aspect, not the Game view's.
            for (int i = 0; i < cameras.Length; i++) cameras[i].aspect = (float)Sizes[i].x / Sizes[i].y;
            return cameras;
        }

        static Camera Find(string name, Camera template)
        {
            var existing = GameObject.Find(name);
            if (existing != null) return existing.GetComponent<Camera>();
            var go = new GameObject(name, typeof(Camera)) { hideFlags = HideFlags.DontSave };
            var camera = go.GetComponent<Camera>();
            camera.CopyFrom(template);
            camera.tag = "Untagged";
            camera.targetTexture = null;
            camera.enabled = false;   // rendered manually into the capture texture only
            camera.fieldOfView = 1f;  // marks it as not yet posed
            return camera;
        }

        // Renders one camera at its capture size and returns the pixels (valid until the next call for that size).
        public static Texture2D Render(Camera camera, int index)
        {
            var size = Sizes[index];
            if (!targets.TryGetValue(size, out var target) || target == null)
            {
                targets[size] = target = new RenderTexture(size.x, size.y, 24, RenderTextureFormat.ARGB32) { antiAliasing = 1 };
                buffers[size] = new Texture2D(size.x, size.y, TextureFormat.RGB24, false);
            }
            var pixels = buffers[size];
            var originalTarget = camera.targetTexture; var originalActive = RenderTexture.active;
            try
            {
                camera.targetTexture = target; camera.Render();
                RenderTexture.active = target; pixels.ReadPixels(new Rect(0, 0, size.x, size.y), 0, 0); pixels.Apply(false);
            }
            finally { camera.targetTexture = originalTarget; RenderTexture.active = originalActive; }
            return pixels;
        }

        public static void Release(Camera lane = null)
        {
            if (lane != null) lane.ResetAspect();
            foreach (var name in new[] { OverheadName, ScanName })
            {
                var existing = GameObject.Find(name);
                if (existing != null) Destroy(existing);
            }
            foreach (var target in targets.Values) if (target != null) { target.Release(); Destroy(target); }
            foreach (var buffer in buffers.Values) if (buffer != null) Destroy(buffer);
            targets.Clear(); buffers.Clear();
        }

        static void Destroy(Object o)
        {
            if (Application.isPlaying) Object.Destroy(o); else Object.DestroyImmediate(o);
        }
    }
}
