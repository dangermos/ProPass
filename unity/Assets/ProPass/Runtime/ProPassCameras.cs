using UnityEngine;

namespace ProPass
{
    // The lane has two cameras. "lane" is the oblique camera saved in the scene. "overhead"
    // looks straight down from the ceiling and is created on demand, so the scene asset stays
    // unchanged. Both are captured for every frame; ids match vision/cameras.json.
    public static class ProPassCameras
    {
        public static readonly string[] Ids = { "lane", "overhead" };
        public const string OverheadName = "Overhead Camera";
        // Products are carried near this height; calibration maps image points onto this plane.
        public const float CarryPlaneY = .9f;

        // Projections (calibration, ground truth) must use the capture aspect, not the Game view's.
        public static void UseCaptureAspect(Camera[] cameras, int width, int height)
        {
            foreach (var camera in cameras) camera.aspect = (float)width / height;
        }

        public static Camera[] Ensure(Camera lane)
        {
            var existing = GameObject.Find(OverheadName);
            Camera overhead = existing != null ? existing.GetComponent<Camera>() : null;
            if (overhead == null)
            {
                var go = new GameObject(OverheadName, typeof(Camera)) { hideFlags = HideFlags.DontSave };
                overhead = go.GetComponent<Camera>();
                overhead.CopyFrom(lane);
                overhead.tag = "Untagged";
                overhead.targetTexture = null;
                overhead.enabled = false;   // rendered manually into the capture texture only
                // Image right is +z (the direction of travel), so the long image side spans the lane.
                go.transform.SetPositionAndRotation(new Vector3(0f, 7.55f, 0f), Quaternion.LookRotation(Vector3.down, Vector3.left));
                overhead.fieldOfView = 50f;
            }
            return new[] { lane, overhead };
        }

        public static void Release(Camera lane = null)
        {
            if (lane != null) lane.ResetAspect();
            var existing = GameObject.Find(OverheadName);
            if (existing == null) return;
            if (Application.isPlaying) Object.Destroy(existing); else Object.DestroyImmediate(existing);
        }
    }
}
