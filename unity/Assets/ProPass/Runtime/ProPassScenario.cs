using System;
using System.Collections.Generic;
using UnityEngine;

namespace ProPass
{
    // A scenario is a deterministic plan: every actor's position is a pure function of
    // (scenario, seed, time). Live Play mode and the offline benchmark recorder both
    // execute the same plan, so a benchmark run can be reproduced exactly.
    public enum ActorKind { Product, Shopper, Hand, Flatbed, Prop }

    public struct Waypoint
    {
        public float t, x, y, z;
        public Waypoint(float t, float x, float y, float z) { this.t = t; this.x = x; this.y = y; this.z = z; }
    }

    public sealed class ActorPlan
    {
        public ActorKind kind;
        public int productIndex = -1;     // index into the simulation's product prefabs
        public string prop = "";          // phone | cup | bag
        public Color tint = Color.gray;
        public int follow = -1;           // when >= 0, path is an offset from that actor
        public float visibleFrom = float.NegativeInfinity, visibleTo = float.PositiveInfinity;
        public float yaw;
        public float sway, swayRate = 1.7f, bob, phase;
        public readonly List<Waypoint> path = new List<Waypoint>();

        public ActorPlan At(float t, float x, float y, float z) { path.Add(new Waypoint(t, x, y, z)); return this; }

        public Vector3 SampleLocal(float t)
        {
            if (path.Count == 0) return Vector3.zero;
            if (t <= path[0].t) return Point(path[0]) + Wobble(t);
            for (int i = 1; i < path.Count; i++)
            {
                if (t > path[i].t) continue;
                var a = path[i - 1]; var b = path[i];
                float u = b.t > a.t ? Mathf.SmoothStep(0f, 1f, (t - a.t) / (b.t - a.t)) : 1f;
                return Vector3.Lerp(Point(a), Point(b), u) + Wobble(t);
            }
            return Point(path[path.Count - 1]) + Wobble(t);
        }

        Vector3 Wobble(float t) => new Vector3(sway * Mathf.Sin(t * swayRate + phase), bob * Mathf.Sin(t * 5.3f + phase * 2f), 0f);
        static Vector3 Point(Waypoint w) => new Vector3(w.x, w.y, w.z);
    }

    public sealed class ScenarioPlan
    {
        public string name, description;
        public int seed;
        public float duration = 18f;
        public float lightIntensity = 2.1f;
        public Color lightColor = Color.white;
        public float cameraShake;
        public int jpegQuality = 85;
        public readonly List<ActorPlan> actors = new List<ActorPlan>();

        public const float LaneHalfWidth = 1.6f;
        public const float ApproachZ = -2.0f;   // orange floor marker
        public const float CommitZ = 1.6f;      // teal floor marker

        public int Add(ActorPlan actor) { actors.Add(actor); return actors.Count - 1; }

        public Vector3 Position(int index, float t)
        {
            var actor = actors[index];
            var local = actor.SampleLocal(t);
            return actor.follow >= 0 ? Position(actor.follow, t) + local : local;
        }

        public bool Visible(int index, float t)
        {
            var actor = actors[index];
            return t >= actor.visibleFrom && t <= actor.visibleTo;
        }

        // Ground truth for scoring, from world-space motion. A product is purchased when it
        // is carried inside the lane, starts behind the approach marker and ends past commit.
        public Dictionary<int, int> ExpectedProductCounts(int knownProducts, out bool reviewExpected)
        {
            var counts = new Dictionary<int, int>();
            reviewExpected = false;
            for (int i = 0; i < actors.Count; i++)
            {
                if (actors[i].kind != ActorKind.Product) continue;
                float minZ = float.PositiveInfinity; bool inLane = true;
                for (float t = 0; t <= duration; t += .125f)
                {
                    var p = Position(i, t);
                    minZ = Mathf.Min(minZ, p.z);
                    if (Mathf.Abs(p.x) > LaneHalfWidth) inLane = false;
                }
                var end = Position(i, duration);
                bool purchased = inLane && minZ <= ApproachZ && end.z >= CommitZ + .4f;
                if (actors[i].productIndex >= knownProducts) { if (inLane) reviewExpected = true; continue; }
                if (purchased) counts[actors[i].productIndex] = counts.TryGetValue(actors[i].productIndex, out int n) ? n + 1 : 1;
            }
            return counts;
        }
    }

    public static class ProPassScenarios
    {
        // The six original demo scenarios keep fixed products so the live checks stay stable.
        public static readonly string[] Classic = { "single", "duplicate", "mixed", "occlusion", "remove", "unknown" };
        // Messy scenarios randomize products, motion, occluders and rendering by seed.
        public static readonly string[] Messy = { "hands", "shopper", "flatbed", "edge", "stacked", "distractors", "bystander", "hesitate" };

        public static IEnumerable<string> All { get { foreach (var s in Classic) yield return s; foreach (var s in Messy) yield return s; } }

        const float CarryY = .9f, StartZ = -3.4f, EndZ = 3.8f;

        public static ScenarioPlan Build(string name, int seed)
        {
            var rng = new System.Random(seed * 7919 + name.GetStableHash());
            float R(float a, float b) => a + (float)rng.NextDouble() * (b - a);
            int Pick(int n) => rng.Next(n);
            bool messy = Array.IndexOf(Messy, name) >= 0;
            var plan = new ScenarioPlan { name = name, seed = seed };
            plan.lightIntensity = messy ? R(1.2f, 2.6f) : R(1.9f, 2.3f);
            plan.lightColor = messy ? Color.Lerp(Color.white, new Color(1f, .86f, .7f), R(0f, .6f)) : Color.white;
            plan.cameraShake = messy ? R(0f, .05f) : 0f;
            plan.jpegQuality = messy ? (int)R(70, 92) : 85;

            ActorPlan Walk(int product, float x, float t0, float walk, float z0 = StartZ, float z1 = EndZ, float y = CarryY)
            {
                var a = new ActorPlan { kind = ActorKind.Product, productIndex = product, yaw = R(-12f, 12f),
                    sway = messy ? R(0f, .08f) : 0f, bob = messy ? R(0f, .03f) : 0f, phase = R(0f, 6.28f) };
                return a.At(0, x, y, z0).At(t0, x, y, z0).At(t0 + walk, x, y, z1);
            }
            int[] Distinct(int n) { var all = new List<int> { 0, 1, 2, 3, 4 }; var r = new int[n]; for (int i = 0; i < n; i++) { int k = Pick(all.Count); r[i] = all[k]; all.RemoveAt(k); } return r; }
            ActorPlan Hand(int follow, float from, float to) => new ActorPlan { kind = ActorKind.Hand, follow = follow, visibleFrom = from, visibleTo = to, tint = new Color(.08f, .1f, .14f) }.At(0, 0, .15f, -.25f);
            Color Shirt() => Color.HSVToRGB(R(0f, 1f), R(.3f, .8f), R(.35f, .85f));

            float start = R(1.4f, 2f), walkTime = messy ? R(10f, 14f) : 12f;
            switch (name)
            {
                case "single":
                    plan.description = "One drill kit, one clean crossing";
                    plan.Add(Walk(0, R(-.15f, .15f), 1.5f, 12f));
                    break;
                case "duplicate":
                    plan.description = "Two identical drill kits side by side";
                    plan.Add(Walk(0, -.48f, 1.5f, 12f)); plan.Add(Walk(0, .48f, 1.5f, 12f));
                    break;
                case "mixed":
                    plan.description = "Drill kit, measuring tape and work gloves";
                    plan.Add(Walk(0, -.8f, 1.5f, 12f)); plan.Add(Walk(2, 0f, 1.5f, 12f)); plan.Add(Walk(4, .8f, 1.5f, 12f));
                    break;
                case "occlusion":
                    plan.description = "A hand hides the drill kit for 0.6 s";
                    var slab = Hand(plan.Add(Walk(0, 0f, 1.5f, 12f)), 7f, 7.6f); slab.prop = "slab"; plan.Add(slab);
                    break;
                case "remove":
                    plan.description = "Driver kit carried in, then carried back out";
                    plan.duration = 30f;
                    plan.Add(Walk(1, 0f, 1.5f, 12f).At(16f, 0f, CarryY, EndZ).At(28f, 0f, CarryY, StartZ));
                    break;
                case "unknown":
                    plan.description = "An unenrolled gray package";
                    plan.Add(Walk(5, 0f, 1.5f, 12f));
                    break;

                case "hands":
                {
                    plan.description = "Hands repeatedly cover the products while they are carried";
                    var products = Distinct(1 + Pick(2));
                    for (int i = 0; i < products.Length; i++)
                    {
                        int p = plan.Add(Walk(products[i], products.Length == 1 ? R(-.4f, .4f) : (i == 0 ? -.5f : .5f), start, walkTime));
                        for (float t = start + R(.5f, 2f); t < start + walkTime; t += R(1.5f, 3.5f))
                            plan.Add(Hand(p, t, t + R(.4f, 1.2f)));
                    }
                    break;
                }
                case "shopper":
                {
                    plan.description = "Another shopper walks across the lane in front of the camera";
                    var products = Distinct(1 + Pick(2));
                    int lead = -1;
                    for (int i = 0; i < products.Length; i++)
                    {
                        int p = plan.Add(Walk(products[i], R(-.6f, .6f), start, walkTime));
                        if (lead < 0) lead = p;
                    }
                    float cross = start + walkTime * R(.3f, .65f), side = Pick(2) == 0 ? -1f : 1f, speed = R(1f, 1.5f);
                    float z = Mathf.Lerp(StartZ, EndZ, (cross - start) / walkTime) - R(.8f, 1.4f);
                    plan.Add(new ActorPlan { kind = ActorKind.Shopper, tint = Shirt(), bob = .03f }
                        .At(0, side * 4.5f, 0, z).At(cross - 4f / speed, side * 4.5f, 0, z).At(cross + 4f / speed, -side * 4.5f, 0, z));
                    break;
                }
                case "flatbed":
                {
                    plan.description = "A flatbed of lumber rolls between the camera and the products for several seconds";
                    var products = Distinct(1 + Pick(3));
                    int lead = -1;
                    for (int i = 0; i < products.Length; i++)
                    {
                        int p = plan.Add(Walk(products[i], products.Length == 1 ? 0f : Mathf.Lerp(-.8f, .8f, i / (float)(products.Length - 1)), start, walkTime));
                        if (lead < 0) lead = p;
                    }
                    float from = start + walkTime * R(.25f, .5f), hold = R(1.5f, 3f), side = Pick(2) == 0 ? -1f : 1f;
                    plan.Add(new ActorPlan { kind = ActorKind.Flatbed, follow = lead, tint = new Color(.82f, .68f, .46f) }
                        .At(0, side * 6f, -CarryY, -1.3f).At(from - 1.5f, side * 6f, -CarryY, -1.3f)
                        .At(from, 0f, -CarryY, -1.3f).At(from + hold, 0f, -CarryY, -1.3f).At(from + hold + 1.5f, -side * 6f, -CarryY, -1.3f));
                    break;
                }
                case "edge":
                {
                    plan.description = "Products enter from below the frame and hug the lane rail";
                    var products = Distinct(1 + Pick(2));
                    float side = Pick(2) == 0 ? -1f : 1f;
                    for (int i = 0; i < products.Length; i++)
                        plan.Add(Walk(products[i], side * R(1.15f, 1.45f), start + i * R(.5f, 2f), walkTime, -5.6f, EndZ, R(.7f, 1.15f)));
                    break;
                }
                case "stacked":
                {
                    plan.description = "One package carried on top of another";
                    int bottom = Pick(5), top = Pick(2) == 0 ? bottom : Pick(5);
                    int b = plan.Add(Walk(bottom, R(-.4f, .4f), start, walkTime, StartZ, EndZ, .78f));
                    var stackedTop = new ActorPlan { kind = ActorKind.Product, productIndex = top, follow = b, yaw = R(-20f, 20f) };
                    plan.Add(stackedTop.At(0, R(-.06f, .06f), .46f, R(-.04f, .04f)));
                    break;
                }
                case "distractors":
                {
                    plan.description = "A phone, a coffee cup and a bag travel through the lane with the products";
                    var products = Distinct(1 + Pick(2));
                    int lead = -1;
                    for (int i = 0; i < products.Length; i++)
                    {
                        int p = plan.Add(Walk(products[i], products.Length == 1 ? R(-.3f, .3f) : (i == 0 ? -.55f : .55f), start, walkTime));
                        if (lead < 0) lead = p;
                    }
                    string[] props = { "phone", "cup", "bag" };
                    foreach (var prop in props)
                    {
                        if (Pick(4) == 0) continue;
                        plan.Add(new ActorPlan { kind = ActorKind.Prop, prop = prop, follow = lead, tint = prop == "bag" ? new Color(.45f, .36f, .26f) : prop == "cup" ? new Color(.92f, .92f, .9f) : new Color(.05f, .05f, .06f) }
                            .At(0, R(-.9f, .9f), prop == "bag" ? -.35f : R(-.05f, .15f), R(-.35f, .35f)));
                    }
                    break;
                }
                case "bystander":
                {
                    plan.description = "A shopper in the next aisle carries a product past the lane; it must not be charged";
                    var products = Distinct(2);
                    plan.Add(Walk(products[0], R(-.4f, .4f), start, walkTime));
                    float side = Pick(2) == 0 ? -1f : 1f, x = side * R(2.4f, 2.9f), t0 = R(1f, 4f), walk = R(8f, 12f);
                    bool forward = Pick(2) == 0;
                    int person = plan.Add(new ActorPlan { kind = ActorKind.Shopper, tint = Shirt(), bob = .03f }
                        .At(0, x, 0, forward ? StartZ : EndZ).At(t0, x, 0, forward ? StartZ : EndZ).At(t0 + walk, x, 0, forward ? EndZ : StartZ));
                    plan.Add(new ActorPlan { kind = ActorKind.Product, productIndex = products[1], follow = person, yaw = R(-15f, 15f) }.At(0, -side * .45f, CarryY, -.5f));
                    plan.duration = Mathf.Max(plan.duration, t0 + walk + 3f);
                    break;
                }
                case "hesitate":
                {
                    plan.description = "The customer pauses mid-lane, steps back, then either finishes or turns around";
                    int product = Pick(5);
                    bool completes = rng.NextDouble() < .6;
                    float x = R(-.4f, .4f), mid = R(-.8f, .6f), back = R(-2.9f, -2.5f), t = start;
                    var a = new ActorPlan { kind = ActorKind.Product, productIndex = product, yaw = R(-12f, 12f), sway = R(0f, .06f), phase = R(0f, 6.28f) };
                    a.At(0, x, CarryY, StartZ).At(t, x, CarryY, StartZ);
                    a.At(t += R(4f, 6f), x, CarryY, mid);
                    a.At(t += R(1f, 2.5f), x, CarryY, mid);
                    a.At(t += R(2f, 3f), x, CarryY, back);
                    a.At(t += R(.8f, 2f), x, CarryY, back);
                    a.At(t += R(5f, 7f), x, CarryY, completes ? EndZ : -5.8f);   // turning around walks back out of view
                    plan.Add(a);
                    plan.duration = t + 3f;
                    break;
                }
                default:
                    throw new ArgumentException("Unknown ProPass scenario: " + name);
            }
            if (plan.description == null) plan.description = name;
            // Hold the final state long enough for the tracker to settle after the last crossing.
            float last = 0f;
            foreach (var actor in plan.actors) if (actor.path.Count > 0) last = Mathf.Max(last, actor.path[actor.path.Count - 1].t);
            plan.duration = Mathf.Max(plan.duration, last + 2.5f);
            return plan;
        }

        public static int GetStableHash(this string value)
        {
            unchecked
            {
                uint hash = 2166136261;
                foreach (char c in value) { hash ^= c; hash *= 16777619; }
                return (int)(hash & 0x7fffffff);
            }
        }
    }
}
