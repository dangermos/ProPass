using UnityEngine;

namespace ProPass
{
    // The three carts a customer can push through the lane, and where products sit on each.
    //   Shopping  wire basket on wheels: one or two boxes
    //   Flat      low platform with a push handle: up to three boxes
    //   Lumber    long narrow platform with a center divider: boards along one side, a box at the back
    public enum CartKind { None, Shopping, Flat, Lumber }

    public static class ProPassCarts
    {
        // Package sizes by prefab index (width, height, depth). The scene builder builds the prefabs from these.
        public static readonly Vector3[] ProductSizes = ProPassCatalog.Sizes();

        static readonly Color Orange = new Color(1f, .4f, .1f), Steel = new Color(.55f, .57f, .6f), Dark = new Color(.13f, .14f, .16f);

        public static bool IsBoard(int product) => ProductSizes[product].z > 1f;

        // Height of the surface products rest on.
        public static float DeckY(CartKind kind) => kind == CartKind.Shopping ? .51f : kind == CartKind.Flat ? .24f : .26f;

        // How far behind the cart's center the person pushing it walks.
        public static float PushDistance(CartKind kind) => kind == CartKind.Shopping ? .95f : kind == CartKind.Flat ? 1.12f : 1.45f;

        public static int Capacity(CartKind kind) => kind == CartKind.Shopping ? 2 : 3;

        // Where each product's center sits, relative to the cart's origin (on the floor, under the middle of the deck).
        public static Vector3[] Slots(CartKind kind, int[] products)
        {
            var slots = new Vector3[products.Length];
            float basketFront = .42f;   // boxes in a basket sit against its front wall, label showing between the wires
            int boxes = 0, boards = 0, box = 0, board = 0;
            foreach (int p in products) { if (IsBoard(p)) boards++; else boxes++; }
            for (int i = 0; i < products.Length; i++)
            {
                var size = ProductSizes[products[i]];
                float y = DeckY(kind) + size.y * .5f;
                if (IsBoard(products[i]))
                {
                    // Boards lie along the cart. On a lumber cart they sit to the left of the divider.
                    float x = kind == CartKind.Lumber ? -.19f + .12f * board : -.2f + .14f * board;
                    slots[i] = new Vector3(x, y, kind == CartKind.Lumber ? .3f : 0f);
                    board++;
                    continue;
                }
                float z;
                if (kind == CartKind.Lumber) z = -.72f;
                else if (kind == CartKind.Shopping) { z = basketFront - size.z * .5f; basketFront -= size.z + .03f; }
                else z = boxes == 1 ? .05f : boxes == 2 ? (box == 0 ? .3f : -.3f) : .45f - .45f * box;
                slots[i] = new Vector3(0f, y, z);
                box++;
            }
            return slots;
        }

        public static GameObject Build(ProPassActorFactory f, CartKind kind)
        {
            var root = new GameObject("Scenario " + kind.ToString().ToLowerInvariant() + " cart");
            var t = root.transform;
            void Wheels(float x, float z)
            {
                for (int sx = -1; sx <= 1; sx += 2) for (int sz = -1; sz <= 1; sz += 2)
                    f.Box("Wheel", new Vector3(.13f, .025f, .13f), Dark, t, new Vector3(sx * x, .065f, sz * z), PrimitiveType.Cylinder)
                        .transform.localRotation = Quaternion.Euler(0, 0, 90);
            }
            void Handle(float halfWidth, float z, float from, float to)
            {
                for (int s = -1; s <= 1; s += 2)
                    f.Box("Handle post", new Vector3(.035f, to - from, .035f), Steel, t, new Vector3(s * halfWidth, (from + to) * .5f, z));
                f.Box("Handle", new Vector3(halfWidth * 2f + .04f, .045f, .045f), Orange, t, new Vector3(0, to, z));
            }
            switch (kind)
            {
                case CartKind.Shopping:
                {
                    const float w = .37f, l = .46f, floor = .5f, rim = .96f;
                    f.Box("Basket floor", new Vector3(w * 2f, .02f, l * 2f), Steel * .8f, t, new Vector3(0, floor, 0));
                    // Horizontal wires only: a barcode can still be read between them.
                    for (float y = floor + .19f; y <= rim + .001f; y += .135f)
                    {
                        bool top = y > rim - .05f;
                        float th = top ? .03f : .012f; var color = top ? Orange : Steel;
                        for (int s = -1; s <= 1; s += 2)
                        {
                            f.Box("Wire", new Vector3(th, th, l * 2f), color, t, new Vector3(s * w, y, 0));
                            f.Box("Wire", new Vector3(w * 2f, th, th), color, t, new Vector3(0, y, s * l));
                        }
                    }
                    for (int sx = -1; sx <= 1; sx += 2) for (int sz = -1; sz <= 1; sz += 2)
                    {
                        f.Box("Corner", new Vector3(.02f, rim - floor, .02f), Steel, t, new Vector3(sx * w, (rim + floor) * .5f, sz * l));
                        f.Box("Leg", new Vector3(.03f, floor - .1f, .03f), Steel, t, new Vector3(sx * (w - .05f), (floor + .1f) * .5f, sz * (l - .06f)));
                    }
                    for (int s = -1; s <= 1; s += 2) f.Box("Chassis", new Vector3(.03f, .03f, l * 2f), Steel, t, new Vector3(s * (w - .05f), .17f, 0));
                    f.Box("Lower tray", new Vector3(w * 2f - .12f, .015f, l * 2f - .1f), Steel * .8f, t, new Vector3(0, .185f, 0));
                    Handle(w, -l - .07f, rim - .1f, rim + .08f);
                    Wheels(w - .05f, l - .06f);
                    break;
                }
                case CartKind.Flat:
                {
                    f.Box("Deck", new Vector3(.8f, .06f, 1.35f), Orange, t, new Vector3(0, .21f, 0));
                    f.Box("Deck mat", new Vector3(.72f, .008f, 1.27f), Dark, t, new Vector3(0, .243f, 0));
                    Handle(.36f, -.66f, .24f, 1.07f);
                    Wheels(.32f, .55f);
                    break;
                }
                default:
                {
                    f.Box("Deck", new Vector3(.62f, .06f, 2f), Orange, t, new Vector3(0, .23f, 0));
                    // The divider keeps boards upright or stacked along one side.
                    for (int i = 0; i < 3; i++) f.Box("Divider post", new Vector3(.035f, 1.1f, .035f), Orange, t, new Vector3(.14f, .81f, -.25f + .6f * i));
                    f.Box("Divider rail", new Vector3(.035f, .035f, 1.24f), Orange, t, new Vector3(.14f, 1.36f, .35f));
                    Handle(.27f, -.98f, .26f, 1.07f);
                    Wheels(.25f, .85f);
                    break;
                }
            }
            return root;
        }
    }
}
