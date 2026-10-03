using System;
using UnityEngine;

namespace ProPass
{
    // Simulator identity is ground truth only. The HTTP camera bridge never sends these fields.
    public sealed class ProPassProduct : MonoBehaviour
    {
        public string sku;
        public int classIndex;
        public string physicalId;
        public Color brandColor;
        public Vector3 packageSize;

        public void AssignInstance() => physicalId = Guid.NewGuid().ToString("N");
    }
}
