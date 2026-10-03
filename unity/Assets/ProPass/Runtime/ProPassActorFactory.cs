using System.Collections.Generic;
using UnityEngine;

namespace ProPass
{
    // Procedural geometry for scenario actors (shoppers, hands, a lumber flatbed, props).
    // Shared by the scenario runner and the dataset exporter so training data and test
    // scenarios contain the same kinds of occluders and distractors.
    public sealed class ProPassActorFactory
    {
        readonly Dictionary<Color, Material> materials = new Dictionary<Color, Material>();

        public void Dispose()
        {
            foreach (var material in materials.Values) ProPassScenarioRunner.Destroy(material);
            materials.Clear();
        }

        public GameObject Slab(Color color) => Box("Hand occluder", new Vector3(.88f, .9f, .18f), color, null);

        public Material Mat(Color color)
        {
            if (materials.TryGetValue(color, out var m)) return m;
            m = new Material(Shader.Find("Universal Render Pipeline/Lit")) { color = color };
            m.SetFloat("_Smoothness", .2f);
            return materials[color] = m;
        }

        public GameObject Box(string name, Vector3 size, Color color, Transform parent, Vector3 offset = default, PrimitiveType shape = PrimitiveType.Cube)
        {
            var go = GameObject.CreatePrimitive(shape);
            go.name = name;
            ProPassScenarioRunner.Destroy(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial = Mat(color);
            if (parent != null) go.transform.SetParent(parent, false);
            go.transform.localPosition = offset; go.transform.localScale = size;
            return go;
        }

        public GameObject Shopper(Color shirt)
        {
            var root = new GameObject("Scenario shopper");
            var skin = new Color(.78f, .6f, .48f); var dark = new Color(.12f, .13f, .16f);
            Box("Torso", new Vector3(.5f, .55f, .32f), shirt, root.transform, new Vector3(0, 1.3f, 0), PrimitiveType.Capsule);
            Box("Head", Vector3.one * .28f, skin, root.transform, new Vector3(0, 2.0f, 0), PrimitiveType.Sphere);
            Box("Leg L", new Vector3(.15f, .42f, .15f), dark, root.transform, new Vector3(-.12f, .42f, 0), PrimitiveType.Capsule);
            Box("Leg R", new Vector3(.15f, .42f, .15f), dark, root.transform, new Vector3(.12f, .42f, 0), PrimitiveType.Capsule);
            Box("Arm L", new Vector3(.12f, .35f, .12f), shirt, root.transform, new Vector3(-.34f, 1.25f, 0), PrimitiveType.Capsule);
            Box("Arm R", new Vector3(.12f, .35f, .12f), shirt, root.transform, new Vector3(.34f, 1.25f, 0), PrimitiveType.Capsule);
            return root;
        }

        public GameObject Arm(Color sleeve)
        {
            var root = new GameObject("Scenario hand");
            Box("Forearm", new Vector3(.62f, .2f, .16f), sleeve, root.transform);
            Box("Hand", new Vector3(.2f, .16f, .18f), new Color(.78f, .6f, .48f), root.transform, new Vector3(.38f, 0, 0), PrimitiveType.Sphere);
            return root;
        }

        public GameObject Flatbed(Color wood)
        {
            var root = new GameObject("Scenario lumber flatbed");
            var orange = new Color(1f, .36f, .12f); var steel = new Color(.2f, .22f, .25f);
            Box("Deck", new Vector3(2.4f, .08f, .8f), orange, root.transform, new Vector3(0, .32f, 0));
            for (int s = -1; s <= 1; s += 2)
            {
                Box("Upright", new Vector3(.06f, 2f, .06f), orange, root.transform, new Vector3(s * 1.1f, 1.3f, -.35f));
                Box("Upright", new Vector3(.06f, 2f, .06f), orange, root.transform, new Vector3(s * 1.1f, 1.3f, .35f));
                Box("Wheel", new Vector3(.22f, .05f, .22f), steel, root.transform, new Vector3(s * 1f, .12f, 0), PrimitiveType.Cylinder).transform.localRotation = Quaternion.Euler(90, 0, 0);
            }
            // Upright sheets of plywood and stacked boards fill most of the view.
            for (int i = 0; i < 4; i++) Box("Plywood", new Vector3(2.2f, 1.9f - i * .25f, .04f), wood * (1f - i * .06f), root.transform, new Vector3(0, 1.32f - i * .12f, -.2f + i * .08f));
            for (int i = 0; i < 6; i++) Box("Board", new Vector3(2.3f, .08f, .14f), wood * .9f, root.transform, new Vector3(0, .4f + i * .085f, .25f));
            Box("Handle", new Vector3(.05f, .9f, .7f), steel, root.transform, new Vector3(1.25f, .8f, 0));
            return root;
        }

        public GameObject Prop(string kind, Color color)
        {
            var root = new GameObject("Scenario prop " + kind);
            switch (kind)
            {
                case "phone": Box("Phone", new Vector3(.09f, .17f, .015f), color, root.transform).transform.localRotation = Quaternion.Euler(-60, 0, 0); break;
                case "cup":
                    Box("Cup", new Vector3(.09f, .07f, .09f), color, root.transform, default, PrimitiveType.Cylinder);
                    Box("Lid", new Vector3(.095f, .01f, .095f), new Color(.1f, .1f, .1f), root.transform, new Vector3(0, .075f, 0), PrimitiveType.Cylinder);
                    break;
                default:
                    Box("Bag", new Vector3(.42f, .38f, .16f), color, root.transform);
                    Box("Strap", new Vector3(.03f, .3f, .03f), color * .7f, root.transform, new Vector3(0, .32f, 0));
                    break;
            }
            return root;
        }
    }
}
