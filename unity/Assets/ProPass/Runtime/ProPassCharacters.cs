using System;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

namespace ProPass
{
    // Optional animated people. The prefab and clips come from an Asset Store pack that is not
    // part of this repository, so every reference here is a plain GameObject or AnimationClip
    // assigned by the scene builder when the pack is present. When they are missing, the
    // simulation falls back to the built-in capsule people.
    // One wearable piece: a skinned mesh that fits a named slot on the base character.
    [Serializable]
    public sealed class ProPassCharacterPart
    {
        public string slot;
        public Mesh mesh;
    }

    [Serializable]
    public sealed class ProPassCharacterSet
    {
        public GameObject prefab;       // the base humanoid: an Animator plus one skinned renderer per slot
        public ProPassCharacterPart[] parts = new ProPassCharacterPart[0];
        public AnimationClip walk, idle;
        public float height = 1.75f;

        public bool Available => prefab != null && walk != null && idle != null;
    }

    // One character whose pose is a pure function of time. Nothing ticks on its own: the caller
    // gives a position, a velocity and a time, and the same inputs always give the same pose.
    // That keeps offline benchmark recordings exactly repeatable.
    public sealed class ProPassCharacter
    {
        public readonly GameObject Root;
        readonly ProPassCharacterSet set;
        readonly float phase;
        PlayableGraph graph;
        AnimationClipPlayable walk, idle;
        AnimationMixerPlayable mixer;
        float facing;

        // Slots every character wears, and slots that only some do (with how often, out of 8).
        static readonly string[] Always = { "T_Shirt", "Pants", "Shoes", "Hairstyle", "Faces" };
        // Hats are left out on purpose: from the lane camera a straw hat showing above a carried
        // box is read as a small yellow product. See "Open problems" in HANDOFF.md.
        static readonly string[] Sometimes = { "Outerwear", "Glasses", "Mustache", "Gloves" };
        static readonly int[] Odds = { 4, 2, 2, 1 };
        static readonly string[] Tinted = { "T_Shirt", "Outerwear", "Pants" };

        public ProPassCharacter(ProPassCharacterSet set, int look, Color tint)
        {
            this.set = set;
            Root = UnityEngine.Object.Instantiate(set.prefab);
            Root.name = "Scenario character";
            var bounds = new Bounds(Root.transform.position, Vector3.zero);
            var random = new System.Random(look * 7919 + 13);
            foreach (var renderer in Root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                renderer.updateWhenOffscreen = true;    // never culled out of a label or scan render
                string slot = renderer.name;
                int roll = random.Next(8), pick = random.Next(1 << 16);
                int sometimes = Array.IndexOf(Sometimes, slot);
                bool worn = slot == "Body" || Array.IndexOf(Always, slot) >= 0 || (sometimes >= 0 && roll < Odds[sometimes]);
                if (worn && slot != "Body")
                {
                    // Every piece shares the base skeleton, so dressing is swapping the slot's mesh.
                    var choices = Array.FindAll(set.parts, part => part.slot == slot && part.mesh != null);
                    worn = choices.Length > 0;
                    if (worn) renderer.sharedMesh = choices[pick % choices.Length].mesh;
                }
                renderer.gameObject.SetActive(worn);
                if (!worn) continue;
                bounds.Encapsulate(renderer.bounds);
                var block = new MaterialPropertyBlock();
                renderer.GetPropertyBlock(block);
                block.SetColor("_BaseColor", Color.Lerp(Color.white, tint, Array.IndexOf(Tinted, slot) >= 0 ? .55f : 0f));
                renderer.SetPropertyBlock(block);
            }
            if (bounds.size.y > .1f) Root.transform.localScale *= set.height / bounds.size.y;
            phase = (look % 17) * .37f;

            var animator = Root.GetComponentInChildren<Animator>();
            animator.runtimeAnimatorController = null;  // the plan drives motion, not a controller
            animator.applyRootMotion = false;
            animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            graph = PlayableGraph.Create("ProPass character");
            graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
            walk = AnimationClipPlayable.Create(graph, set.walk);
            idle = AnimationClipPlayable.Create(graph, set.idle);
            mixer = AnimationMixerPlayable.Create(graph, 2);
            graph.Connect(walk, 0, mixer, 0);
            graph.Connect(idle, 0, mixer, 1);
            AnimationPlayableOutput.Create(graph, "pose", animator).SetSourcePlayable(mixer);
        }

        public void Face(float yawDegrees) => facing = yawDegrees;

        // keepFacing: walk without turning toward the direction of travel (pushing or pulling a cart).
        public void Pose(Vector3 position, Vector3 velocity, float t, bool keepFacing = false)
        {
            velocity.y = 0f;
            float speed = velocity.magnitude;
            bool moving = speed > .08f;
            if (moving && !keepFacing) facing = Mathf.Atan2(velocity.x, velocity.z) * Mathf.Rad2Deg;
            Root.transform.SetPositionAndRotation(new Vector3(position.x, 0f, position.z), Quaternion.Euler(0f, facing, 0f));
            mixer.SetInputWeight(0, moving ? 1f : 0f);
            mixer.SetInputWeight(1, moving ? 0f : 1f);
            // Stride rate follows walking speed, so feet roughly keep up with the ground.
            walk.SetTime(Mathf.Repeat((t + phase) * Mathf.Clamp(speed / 1.2f, .35f, 1.4f), set.walk.length));
            idle.SetTime(Mathf.Repeat(t + phase, set.idle.length));
            graph.Evaluate(0f);
        }

        public void Dispose()
        {
            if (graph.IsValid()) graph.Destroy();
            ProPassScenarioRunner.Destroy(Root);
        }
    }
}
