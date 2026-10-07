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
        readonly ProPassActorFactory actors;
        readonly GameObject avatar;     // animated stand-in for the capsule customer, when characters are available
        Camera camera; Light light; Transform customer;
        Vector3 cameraPosition; Quaternion cameraRotation; float baseLight = 2.1f; Color baseLightColor = Color.white;

        public ProPassScenarioRunner(ScenarioPlan plan, GameObject[] productPrefabs, Camera camera, Light light, Transform customer,
                                     ProPassCharacterSet characters = null)
        {
            Plan = plan; this.camera = camera; this.light = light; this.customer = customer;
            actors = new ProPassActorFactory(characters);
            avatar = actors.CustomerAvatar(customer, plan.seed);
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
                    case ActorKind.Shopper: go = actors.Shopper(actor.tint, plan.seed * 31 + i + 1); break;
                    case ActorKind.Hand: go = actor.prop == "slab" ? actors.Slab(actor.tint) : actors.Arm(actor.tint); break;
                    case ActorKind.Flatbed: go = actors.Flatbed(actor.tint); break;
                    case ActorKind.Cart: go = ProPassCarts.Build(actors, plan.cart); break;
                    default: go = actors.Prop(actor.prop, actor.tint); break;
                }
                if (actor.kind != ActorKind.Product) spawned.Add(go);
                actorObjects[i] = go;
            }
            Apply(0f);
        }

        public void Apply(float t)
        {
            t = Mathf.Clamp(t, 0f, Plan.duration);
            Vector3 lead = Vector3.zero, leadVelocity = Vector3.zero; bool hasLead = false, longLead = false;
            for (int i = 0; i < actorObjects.Length; i++)
            {
                var go = actorObjects[i];
                if (go == null) continue;
                bool visible = Plan.Visible(i, t);
                if (go.activeSelf != visible) go.SetActive(visible);
                var position = Plan.Position(i, t);
                var actor = Plan.actors[i];
                if (actor.kind == ActorKind.Shopper) actors.Pose(go, position, Velocity(i, t), t);
                else go.transform.position = position;
                if (actor.kind == ActorKind.Product && !hasLead && Mathf.Abs(position.x) <= ScenarioPlan.LaneHalfWidth && actor.follow < 0)
                { lead = position; leadVelocity = Velocity(i, t); hasLead = true; longLead = actor.productIndex >= ProPassScenarios.Lumber; }
            }
            // Without a cart, the customer carries the first product in front of them
            // (a board at their side: nobody walks through their own lumber).
            if (customer != null && hasLead && Plan.cartActor < 0) customer.position = longLead
                ? new Vector3(lead.x - .5f, 0f, lead.z - .2f)
                : new Vector3(lead.x, 0f, lead.z - .6f);
            // With a cart, the customer walks behind its handle and keeps facing the way the cart points.
            bool pushing = customer != null && Plan.cartActor >= 0;
            if (pushing)
            {
                var cart = Plan.Position(Plan.cartActor, t);
                customer.position = new Vector3(cart.x, 0f, cart.z - ProPassCarts.PushDistance(Plan.cart));
                actors.Pose(avatar, customer.position, Velocity(Plan.cartActor, t), t, 0f, true);
            }
            else if (customer != null) actors.Pose(avatar, customer.position, hasLead ? leadVelocity : Vector3.zero, t);
            if (camera != null && Plan.cameraShake > 0f)
            {
                float s = Plan.cameraShake, k = Plan.seed * .37f;
                var shake = new Vector3(Mathf.PerlinNoise(t * 2.1f, k) - .5f, Mathf.PerlinNoise(k, t * 2.3f) - .5f, Mathf.PerlinNoise(t * 1.7f, k + 3f) - .5f) * 2f * s;
                camera.transform.SetPositionAndRotation(cameraPosition + shake, cameraRotation * Quaternion.Euler(shake.y * 8f, shake.x * 8f, 0f));
            }
        }

        // Velocity from the plan itself, so a pose depends only on (scenario, seed, time).
        Vector3 Velocity(int actor, float t)
        {
            float a = Mathf.Max(0f, t - .06f), b = Mathf.Min(Plan.duration, t + .06f);
            return b > a ? (Plan.Position(actor, b) - Plan.Position(actor, a)) / (b - a) : Vector3.zero;
        }

        public void Dispose()
        {
            foreach (var go in Products) Destroy(go);
            foreach (var go in spawned) Destroy(go);
            actors.Dispose();
            Products.Clear(); spawned.Clear();
            if (camera != null) camera.transform.SetPositionAndRotation(cameraPosition, cameraRotation);
            if (light != null) { light.intensity = baseLight; light.color = baseLightColor; }
        }

        internal static void Destroy(Object o)
        {
            if (o == null) return;
            if (Application.isPlaying) Object.Destroy(o); else Object.DestroyImmediate(o);
        }

    }
}
