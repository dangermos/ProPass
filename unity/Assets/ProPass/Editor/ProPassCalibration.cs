using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace ProPass.Editor
{
    // Writes vision/cameras.json: for each camera, point pairs between the carry-height plane
    // (world x, z in meters) and the image (normalized, top-left origin), plus the camera's
    // footprint on that plane. Python fits a homography from the pairs, so inference can place
    // detections in lane coordinates. Geometry only: no product, SKU or identity data.
    public static class ProPassCalibration
    {
        const float Bound = 9f;   // footprints are clipped to this many meters from the lane center

        [MenuItem("ProPass/Export camera calibration")]
        public static void ExportFromMenu()
        {
            string path = EditorUtility.SaveFilePanel("Camera calibration (propass/vision/cameras.json)", "", "cameras", "json");
            if (!string.IsNullOrEmpty(path)) Export(path);
        }

        public static string Export(string path)
        {
            var simulation = UnityEngine.Object.FindFirstObjectByType<ProPassSimulation>() ?? throw new InvalidOperationException("Open the Checkout scene first.");
            var cameras = ProPassCameras.Ensure(simulation.checkoutCamera);
            var plane = new Plane(Vector3.up, new Vector3(0, ProPassCameras.CarryPlaneY, 0));
            string F(float v) => v.ToString("F5", CultureInfo.InvariantCulture);
            var json = new StringBuilder("{\n  \"plane_height\": " + F(ProPassCameras.CarryPlaneY) + ",\n");
            json.Append("  \"lane\": {\"half_width\": " + F(ScenarioPlan.LaneHalfWidth) + ", \"approach_z\": " + F(ScenarioPlan.ApproachZ) + ", \"commit_z\": " + F(ScenarioPlan.CommitZ) + "},\n  \"cameras\": [\n");
            for (int c = 0; c < cameras.Length; c++)
            {
                var camera = cameras[c];
                var pairs = new List<string>();
                for (float x = -3f; x <= 3.01f; x += 1.5f)
                for (float z = -5f; z <= 5.01f; z += 2.5f)
                {
                    var v = camera.WorldToViewportPoint(new Vector3(x, ProPassCameras.CarryPlaneY, z));
                    if (v.z > 0) pairs.Add($"[{F(x)}, {F(z)}, {F(v.x)}, {F(1f - v.y)}]");
                }
                // Walk the image border and drop each ray onto the plane to get the visible footprint.
                var footprint = new List<string>();
                var border = new List<Vector2>();
                for (int i = 0; i <= 8; i++) border.Add(new Vector2(i / 8f, 0));
                for (int i = 1; i <= 8; i++) border.Add(new Vector2(1, i / 8f));
                for (int i = 7; i >= 0; i--) border.Add(new Vector2(i / 8f, 1));
                for (int i = 7; i >= 1; i--) border.Add(new Vector2(0, i / 8f));
                foreach (var b in border)
                {
                    var ray = camera.ViewportPointToRay(new Vector3(b.x, b.y, 0));
                    Vector3 hit = plane.Raycast(ray, out float d) ? ray.GetPoint(d) : ray.GetPoint(100f);
                    footprint.Add($"[{F(Mathf.Clamp(hit.x, -Bound, Bound))}, {F(Mathf.Clamp(hit.z, -Bound, Bound))}]");
                }
                var p = camera.transform.position;
                json.Append("    {\"id\": \"" + ProPassCameras.Ids[c] + "\", \"width\": " + ProPassCameras.Sizes[c].x + ", \"height\": " + ProPassCameras.Sizes[c].y +
                    ", \"position\": [" + F(p.x) + ", " + F(p.y) + ", " + F(p.z) + "],\n      \"plane_to_image\": [" + string.Join(", ", pairs) +
                    "],\n      \"footprint\": [" + string.Join(", ", footprint) + "]}" + (c < cameras.Length - 1 ? ",\n" : "\n"));
            }
            json.Append("  ]\n}\n");
            File.WriteAllText(path, json.ToString());
            if (!Application.isPlaying) ProPassCameras.Release(simulation.checkoutCamera);
            Debug.Log("ProPass calibration written: " + path);
            return path;
        }
    }
}
