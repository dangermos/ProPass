using System.Collections.Generic;
using UnityEngine;

namespace ProPass
{
    // Spawns the actors of a ScenarioPlan and poses them for any time t. Works in Play mode
    // (live demo) and in Edit mode (offline benchmark recorder).
    public sealed class ProPassScenarioRunner
    {
        public ScenarioPlan Plan { get; private set; }
        public readonly List<GameObject> Products = new List<GameObject>();
        public readonly List<int> ProductActorIndices = new List<int>();

        readonly List<GameObject> spawned = new List<GameObject>();
        readonly GameObject[] actorObjects;
        readonly Dictionary<Color, Material> materials = new Dictionary<Color, Material>();
        Camera camera; Light light; Transform customer;
        Vector3 cameraPosition; Quaternion cameraRotation; float baseLight = 2.1f; Color baseLightColor = Color.white;

        public ProPassScenarioRunner(ScenarioPlan plan, GameObject[] productPrefabs, Camera camera, Light light, Transform customer)
        {
            Plan = plan; this.camera = camera; this.light = light; this.customer = customer;
            if (camera != null) { cameraPosition = camera.transform.position; cameraRotation = camera.transform.rotation; }
            if (light != null) { baseLight = light.intensity; baseLightColor = light.color; light.intensity = plan.lightIntensity; light.color = plan.lightColor; }
            actorObjects = new GameObject[plan.actors.Count];
            for (int i = 0; i < plan.actors.Count; i++)
            {
                var actor = plan.actors[i];
                GameObject go;
                switch (actor.kind)
                {
                    case ActorKind.Product:
                        go = Object.Instantiate(productPrefabs[actor.productIndex]);
                        go.name = "Scenario product " + i;
                        go.GetComponent<ProPassProduct>().AssignInstance();
                        go.transform.rotation = Quaternion.Euler(0f, actor.yaw, 0f);
                        Products.Add(go); ProductActorIndices.Add(i);
                        break;
                    case ActorKind.Shopper: go = Shopper(actor.tint); break;
                    case ActorKind.Hand: go = actor.prop == "slab" ? Box("Hand occluder", new Vector3(.88f, .9f, .18f), actor.tint, null) : Arm(actor.tint); break;
                    case ActorKind.Flatbed: go = Flatbed(actor.tint); break;
                    default: go = Prop(actor.prop, actor.tint); break;
                }
                if (actor.kind != ActorKind.Product) spawned.Add(go);
                actorObjects[i] = go;
            }
            Apply(0f);
        }

        public void Apply(float t)
        {
            t = Mathf.Clamp(t, 0f, Plan.duration);
            Vector3 lead = Vector3.zero; bool hasLead = false;
            for (int i = 0; i < actorObjects.Length; i++)
            {
                var go = actorObjects[i];
                if (go == null) continue;
                bool visible = Plan.Visible(i, t);
                if (go.activeSelf != visible) go.SetActive(visible);
                var position = Plan.Position(i, t);
                go.transform.position = position;
                var actor = Plan.actors[i];
                if (actor.kind == ActorKind.Product && !hasLead && Mathf.Abs(position.x) <= ScenarioPlan.LaneHalfWidth && actor.follow < 0)
                { lead = position; hasLead = true; }
            }
            // The scene's customer proxy walks just behind the first product in the lane.
            if (customer != null && hasLead) customer.position = new Vector3(lead.x * .3f, 0f, lead.z + .65f);
            if (camera != null && Plan.cameraShake > 0f)
            {
                float s = Plan.cameraShake, k = Plan.seed * .37f;
                var shake = new Vector3(Mathf.PerlinNoise(t * 2.1f, k) - .5f, Mathf.PerlinNoise(k, t * 2.3f) - .5f, Mathf.PerlinNoise(t * 1.7f, k + 3f) - .5f) * 2f * s;
                camera.transform.SetPositionAndRotation(cameraPosition + shake, cameraRotation * Quaternion.Euler(shake.y * 8f, shake.x * 8f, 0f));
            }
        }

        public void Dispose()
        {
            foreach (var go in Products) Destroy(go);
            foreach (var go in spawned) Destroy(go);
            foreach (var material in materials.Values) Destroy(material);
            Products.Clear(); spawned.Clear(); materials.Clear();
            if (camera != null) camera.transform.SetPositionAndRotation(cameraPosition, cameraRotation);
            if (light != null) { light.intensity = baseLight; light.color = baseLightColor; }
        }

        static void Destroy(Object o)
        {
            if (o == null) return;
            if (Application.isPlaying) Object.Destroy(o); else Object.DestroyImmediate(o);
        }

        Material Mat(Color color)
        {
            if (materials.TryGetValue(color, out var m)) return m;
            m = new Material(Shader.Find("Universal Render Pipeline/Lit")) { color = color };
            m.SetFloat("_Smoothness", .2f);
            return materials[color] = m;
        }

        GameObject Box(string name, Vector3 size, Color color, Transform parent, Vector3 offset = default, PrimitiveType shape = PrimitiveType.Cube)
        {
            var go = GameObject.CreatePrimitive(shape);
            go.name = name;
            Destroy(go.GetComponent<Collider>());
            go.GetComponent<Renderer>().sharedMaterial = Mat(color);
            if (parent != null) go.transform.SetParent(parent, false);
            go.transform.localPosition = offset; go.transform.localScale = size;
            return go;
        }

        GameObject Shopper(Color shirt)
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

        GameObject Arm(Color sleeve)
        {
            var root = new GameObject("Scenario hand");
            Box("Forearm", new Vector3(.62f, .2f, .16f), sleeve, root.transform);
            Box("Hand", new Vector3(.2f, .16f, .18f), new Color(.78f, .6f, .48f), root.transform, new Vector3(.38f, 0, 0), PrimitiveType.Sphere);
            return root;
        }

        GameObject Flatbed(Color wood)
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

        GameObject Prop(string kind, Color color)
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
