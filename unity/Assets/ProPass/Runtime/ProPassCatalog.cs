using UnityEngine;

namespace ProPass
{
    public enum PackageShape { Box, Drum, Board }

    public sealed class CatalogItem
    {
        public string sku, name, brand;
        public int classIndex;          // must match catalog.json; -1 for the unenrolled package
        public Color color;
        public Vector3 size;            // width, height, depth of the package
        public PackageShape shape;

        public CatalogItem(string sku, string brand, string name, int classIndex, Color color, Vector3 size, PackageShape shape = PackageShape.Box)
        { this.sku = sku; this.brand = brand; this.name = name; this.classIndex = classIndex; this.color = color; this.size = size; this.shape = shape; }
    }

    // Every product the lane knows, in prefab order. All brands and products are invented for this project.
    // Skus, names and class indices must match catalog.json; scripts/prepare_products.py draws the label art.
    //   0 .. Ordinary-1   boxed and drum products that scan like any other
    //   Unknown           a package that is not in the catalog
    //   Locked            a restricted tool an associate must release
    //   Lumber, Treated   bare boards with no barcode
    public static class ProPassCatalog
    {
        static Color C(float r, float g, float b) => new Color(r, g, b);
        static Vector3 S(float x, float y, float z) => new Vector3(x, y, z);

        public static readonly CatalogItem[] Items =
        {
            new CatalogItem("PEX-001", "VOLTARA",      "DRILL KIT",        0, C(.93f, .24f, .18f), S(.67f, .48f, .39f)),
            new CatalogItem("PEX-002", "VOLTARA",      "IMPACT DRIVER",    1, C(.08f, .58f, .72f), S(.61f, .45f, .34f)),
            new CatalogItem("PEX-003", "GRIPWELL",     "TAPE MEASURE",     2, C(.96f, .71f, .12f), S(.36f, .34f, .18f)),
            new CatalogItem("PEX-004", "HALVARD",      "DECK SCREWS",      3, C(.38f, .27f, .72f), S(.45f, .36f, .29f)),
            new CatalogItem("PEX-005", "GRIPWELL",     "WORK GLOVES",      4, C(.24f, .64f, .35f), S(.45f, .4f, .2f)),
            new CatalogItem("PEX-009", "CINDERLINE",   "INTERIOR PAINT",   8, C(.93f, .93f, .9f),  S(.3f, .37f, .3f), PackageShape.Drum),
            new CatalogItem("PEX-010", "MASON & PINE", "JOINT COMPOUND",   9, C(.45f, .7f, .95f),  S(.34f, .3f, .34f), PackageShape.Drum),
            new CatalogItem("PEX-011", "BRIGHTFORGE",  "LED WORK LIGHT",  10, C(.85f, .2f, .55f),  S(.34f, .52f, .24f)),
            new CatalogItem("PEX-012", "VOLTARA",      "CIRCULAR SAW",    11, C(.12f, .2f, .5f),   S(.56f, .36f, .34f)),
            new CatalogItem("PEX-013", "MASON & PINE", "CONCRETE MIX",    12, C(.55f, .25f, .18f), S(.6f, .24f, .4f)),
            new CatalogItem("PEX-014", "CINDERLINE",   "CAULK 12-PACK",   13, C(.98f, .65f, .7f),  S(.34f, .28f, .26f)),
            new CatalogItem("PEX-015", "GRIPWELL",     "SAFETY KIT",      14, C(.7f, .9f, .2f),    S(.4f, .3f, .16f)),
            new CatalogItem("UNKNOWN", "",             "UNENROLLED",      -1, C(.6f, .59f, .56f),  S(.52f, .4f, .3f)),
            new CatalogItem("PEX-006", "VOLTARA",      "DEMOLITION HAMMER", 5, C(.16f, .18f, .22f), S(.58f, .42f, .3f)),
            new CatalogItem("PEX-007", "",             "2x4 STUD",         6, C(.86f, .74f, .52f), S(.09f, .04f, 1.2f), PackageShape.Board),
            new CatalogItem("PEX-008", "",             "2x4 TREATED",      7, C(.45f, .5f, .3f),   S(.09f, .04f, 1.2f), PackageShape.Board),
        };

        public const int Ordinary = 12, Unknown = 12, Locked = 13, Lumber = 14, TreatedLumber = 15;

        public static Vector3[] Sizes()
        {
            var sizes = new Vector3[Items.Length];
            for (int i = 0; i < Items.Length; i++) sizes[i] = Items[i].size;
            return sizes;
        }
    }
}
