using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace ProPass.Editor
{
    public static class ProPassSceneBuilder
    {
        public const string Root = "Assets/ProPass";
        // Products come from ProPassCatalog, in prefab order.
        static CatalogItem[] Items => ProPassCatalog.Items;

        [MenuItem("ProPass/Build checkout scene")]
        public static void Build()
        {
            Directory.CreateDirectory(Root + "/Scenes");
            Directory.CreateDirectory(Root + "/Prefabs");
            Directory.CreateDirectory(Root + "/Materials");
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var floor = Mat("Floor", new Color(.42f,.44f,.46f));
            var dark = Mat("Fixtures", new Color(.08f,.1f,.14f));
            var steel = Mat("Steel", new Color(.27f,.32f,.37f));
            var lane = Mat("Lane surface", new Color(.3f,.33f,.37f));
            var wall = Mat("Store wall", new Color(.78f,.78f,.74f));
            var shelfSteel = Mat("Shelf steel", new Color(.2f,.3f,.5f));
            // Muted shelf stock in many colors: it reads as a stocked store without looking like a catalog product.
            var stock = new Material[10];
            for(int k=0;k<stock.Length;k++) stock[k]=Mat("Shelf stock "+k,Color.HSVToRGB(k/(float)stock.Length,.32f,.5f+.25f*(k%3)/2f));
            var kraft = Mat("Shelf carton", new Color(.62f,.5f,.36f));
            var orange = Mat("Signal orange", new Color(1f,.36f,.12f));
            var teal = Mat("Signal teal", new Color(.04f,.75f,.65f));
            var white = Mat("Off white", new Color(.88f,.9f,.89f));
            Cube("Warehouse floor", new Vector3(0,-.15f,0), new Vector3(22,.3f,22), floor);
            // Polished concrete with saw-cut joints.
            for(int k=-5;k<=5;k++)
            {
                Cube("Floor joint",new Vector3(k*2f,.002f,0),new Vector3(.02f,.004f,22),Mat("Floor joint",new Color(.33f,.35f,.37f)));
                Cube("Floor joint",new Vector3(0,.002f,k*2f),new Vector3(22,.004f,.02f),Mat("Floor joint",new Color(.33f,.35f,.37f)));
            }
            Cube("Checkout passage", new Vector3(0,.008f,0),new Vector3(3.2f,.015f,12),lane);
            // Back and side walls, so no camera looks into empty space.
            Cube("Back wall",new Vector3(0,3f,-9.5f),new Vector3(22,6,.3f),wall);
            Cube("Side wall",new Vector3(-10.5f,3f,0),new Vector3(.3f,6,22),wall);
            Cube("Side wall",new Vector3(10.5f,3f,0),new Vector3(.3f,6,22),wall);
            Cube("Wall stripe",new Vector3(0,4.6f,-9.33f),new Vector3(22,.5f,.05f),orange);
            Text("PRO EXPRESS LANE",new Vector3(0,4.6f,-9.28f),.34f,Color.white,Quaternion.identity);
            Text("CONTRACTOR CHECKOUT  ·  KEEP WALKING",new Vector3(0,3.9f,-9.3f),.16f,new Color(.2f,.22f,.26f),Quaternion.identity);
            for(int side=-1;side<=1;side+=2)
            {
                // Two rows of pallet racking each side, stocked with cartons, pails and long goods.
                for(int row=0;row<2;row++)
                for(int z=-7;z<=6;z+=2)
                {
                    float x=side*(6.2f+row*2.4f);   // clear of the strip beside the lane where flatbeds wait and cross
                    Cube("Shelf upright",new Vector3(x,1.6f,z),new Vector3(.1f,3.2f,.1f),shelfSteel);
                    Cube("Shelf upright",new Vector3(x+side*1.1f,1.6f,z),new Vector3(.1f,3.2f,.1f),shelfSteel);
                    for(int level=0;level<4;level++)
                    {
                        float y=.25f+level*.8f;
                        Cube("Shelf beam",new Vector3(x+side*.55f,y,z+1f),new Vector3(1.2f,.07f,2f),orange);
                        for(int k=0;k<4;k++)
                        {
                            int pick=Mathf.Abs((z*7+level*5+k*3+row*11+(side>0?1:0)*13))%13;
                            var position=new Vector3(x+side*.55f,y+.035f,z+.3f+k*.47f);
                            if(pick>=10) Cube("Shelf carton",position+new Vector3(0,.2f,0),new Vector3(.9f,.4f,.4f),kraft);
                            else if(pick%4==3) Primitive("Shelf pail",PrimitiveType.Cylinder,position+new Vector3(0,.17f,0),new Vector3(.3f,.17f,.3f),stock[pick]);
                            else Cube("Shelf stock",position+new Vector3(0,.15f+.05f*(pick%3),0),new Vector3(.7f+.1f*(pick%2),.3f+.1f*(pick%3),.36f),stock[pick]);
                        }
                    }
                    if(z==-1&&row==0)
                    {
                        Cube("Aisle sign",new Vector3(x+side*.55f,3.75f,z+1f),new Vector3(1.5f,.6f,.06f),dark);
                        Text(side<0?"TOOLS":"BUILDING",new Vector3(x+side*.55f,3.75f,z+1.04f),.2f,Color.white,Quaternion.Euler(0,180,0));
                    }
                }
                Cube("Lane rail",new Vector3(side*1.68f,.2f,0),new Vector3(.08f,.4f,10),dark);
                Cube("Lane light",new Vector3(side*1.72f,.42f,0),new Vector3(.035f,.035f,10),teal);
            }
            Cube("Approach marker",new Vector3(0,.03f,-2),new Vector3(3.1f,.025f,.09f),orange);
            Cube("Commit marker",new Vector3(0,.035f,1.6f),new Vector3(3.1f,.025f,.09f),teal);
            for(int i=0;i<5;i++) Cube("Directional marker",new Vector3(0,.026f,-3+i*1.35f),new Vector3(.04f,.012f,.4f),white);
            Cube("Portal left",new Vector3(-1.9f,1.65f,4.6f),new Vector3(.2f,3.3f,.3f),orange);
            Cube("Portal right",new Vector3(1.9f,1.65f,4.6f),new Vector3(.2f,3.3f,.3f),orange);
            Cube("Portal header",new Vector3(0,3.2f,4.6f),new Vector3(4,.35f,.3f),dark);
            Text("PRO EXPRESS",new Vector3(0,3.2f,4.42f),.2f,Color.white,Quaternion.identity);
            // An associate station beside the gate: where a cart goes when the lane asks for help.
            Cube("Associate desk",new Vector3(3.1f,.5f,3.6f),new Vector3(1.4f,1f,.7f),dark);
            Cube("Associate desk top",new Vector3(3.1f,1.02f,3.6f),new Vector3(1.5f,.05f,.8f),orange);
            Cube("Associate screen",new Vector3(3.1f,1.4f,3.75f),new Vector3(.5f,.34f,.04f),teal);

            var cameraObject = new GameObject("Checkout Camera",typeof(Camera),typeof(UniversalAdditionalCameraData));
            cameraObject.tag="MainCamera";
            var camera=cameraObject.GetComponent<Camera>();
            // Above the exit gate, looking back down the lane: customers walk toward it behind
            // their carts, so the person pushing never hides what is on the cart.
            camera.transform.position=new Vector3(0,8f,4.6f);
            camera.transform.LookAt(new Vector3(0,.6f,.3f));
            camera.fieldOfView=56;
            camera.nearClipPlane=.05f; camera.farClipPlane=60;
            camera.clearFlags=CameraClearFlags.SolidColor; camera.backgroundColor=new Color(.2f,.21f,.23f);
            camera.allowHDR=false; camera.allowMSAA=false;
            cameraObject.GetComponent<UniversalAdditionalCameraData>().renderPostProcessing=false;
            var lightObject=new GameObject("Key daylight",typeof(Light));
            var light=lightObject.GetComponent<Light>();light.type=LightType.Directional;light.intensity=2.1f;
            light.transform.rotation=Quaternion.Euler(48,-28,0); light.shadows=LightShadows.Soft;
            RenderSettings.ambientMode=AmbientMode.Flat;RenderSettings.ambientLight=new Color(.56f,.57f,.58f);

            var simulator=new GameObject("ProPass Simulation").AddComponent<ProPassSimulation>();
            simulator.checkoutCamera=camera;
            simulator.productPrefabs=new GameObject[Items.Length];
            for(int i=0;i<Items.Length;i++) simulator.productPrefabs[i]=Product(i);
            var person=new GameObject("Customer proxy — simulated actor");
            var body=Primitive("Torso",PrimitiveType.Capsule,new Vector3(0,1.3f,0),new Vector3(.48f,.5f,.3f),dark);
            body.transform.SetParent(person.transform,true);
            var head=Primitive("Head",PrimitiveType.Sphere,new Vector3(0,2.02f,0),Vector3.one*.3f,white);
            head.transform.SetParent(person.transform,true);
            for(int side=-1;side<=1;side+=2)
            {
                var leg=Primitive("Leg",PrimitiveType.Capsule,new Vector3(side*.13f,.4f,0),new Vector3(.14f,.4f,.14f),dark);
                leg.transform.SetParent(person.transform,true);
                var hand=Primitive("Hand",PrimitiveType.Sphere,new Vector3(side*.91f,.97f,-.7f),Vector3.one*.15f,white);
                hand.transform.SetParent(person.transform,true);
            }
            person.transform.position=new Vector3(0,0,-2.75f);
            simulator.customer=person.transform;
            // Optional Asset Store characters (not part of this repository). Missing files leave the capsule people.
            const string pack="Assets/ithappy/Creative_Characters_FREE/";
            // Wearable pieces, by folder. Each fits one slot of the base character.
            var slots=new System.Collections.Generic.Dictionary<string,string>{{"Outfit","T_Shirt"},{"Outwear","Outerwear"},{"Pants","Pants"},{"Shorts","Pants"},
                {"Shoes","Shoes"},{"Hairstyle","Hairstyle"},{"Hat","Hat"},{"Glasses","Glasses"},{"Gloves","Gloves"},{"Faces","Faces"},{"Face Accessories","Mustache"}};
            var parts=new System.Collections.Generic.List<ProPassCharacterPart>();
            foreach(var folder in slots)
            {
                if(!AssetDatabase.IsValidFolder(pack+"Prefabs/"+folder.Key))continue;
                foreach(string guid in AssetDatabase.FindAssets("t:Prefab",new[]{pack+"Prefabs/"+folder.Key}))
                {
                    var piece=AssetDatabase.LoadAssetAtPath<GameObject>(AssetDatabase.GUIDToAssetPath(guid));
                    var skin=piece!=null?piece.GetComponentInChildren<SkinnedMeshRenderer>(true):null;
                    if(skin==null||skin.sharedMesh==null)continue;
                    if(folder.Key=="Face Accessories"&&!piece.name.StartsWith("Mustache"))continue;
                    parts.Add(new ProPassCharacterPart{slot=folder.Value,mesh=skin.sharedMesh});
                }
            }
            simulator.characters=new ProPassCharacterSet{
                parts=parts.ToArray(),
                prefab=AssetDatabase.LoadAssetAtPath<GameObject>(pack+"Prefabs/Base_Mesh.prefab"),
                walk=AssetDatabase.LoadAssetAtPath<AnimationClip>(pack+"Animations/Other_Animations/Walk_Forward.anim"),
                idle=AssetDatabase.LoadAssetAtPath<AnimationClip>(pack+"Animations/Other_Animations/Idle_Breathing.anim")};
            var occluder=Cube("Temporary hand occluder",new Vector3(0,1,0),new Vector3(.88f,.9f,.18f),dark);
            occluder.SetActive(false);simulator.occluder=occluder.transform;
            EditorSceneManager.SaveScene(scene,Root+"/Scenes/Checkout.unity");
            EditorBuildSettings.scenes=new[]{new EditorBuildSettingsScene(Root+"/Scenes/Checkout.unity",true)};
            AssetDatabase.SaveAssets();
            Selection.activeGameObject=simulator.gameObject;
        }

        static GameObject Product(int i)
        {
            var item=Items[i];var size=item.size;var color=item.color;
            var root=new GameObject("Product "+item.name);
            var p=root.AddComponent<ProPassProduct>();p.sku=item.sku;
            p.classIndex=item.classIndex;p.brandColor=color;p.packageSize=size;
            string path=Root+"/Prefabs/Product"+i+".prefab";
            if(item.shape==PackageShape.Board)
            {
                // Lumber: a bare board with darker end grain, no packaging and no barcode.
                var board=Cube("Board",Vector3.zero,size,Mat("Product "+i,color));board.transform.SetParent(root.transform,false);
                for(int end=-1;end<=1;end+=2)
                {
                    var grain=Cube("End grain",new Vector3(0,0,end*(size.z*.5f+.002f)),new Vector3(size.x,size.y,.004f),Mat("Product grain "+i,color*.7f));
                    grain.transform.SetParent(root.transform,false);
                }
                var boardPrefab=PrefabUtility.SaveAsPrefabAsset(root,path);UnityEngine.Object.DestroyImmediate(root);return boardPrefab;
            }
            bool drum=item.shape==PackageShape.Drum;
            if(drum)
            {
                // A pail or can: a cylinder with a darker lid and a wire handle, label on the side facing the gate.
                var pail=Primitive("Package",PrimitiveType.Cylinder,Vector3.zero,new Vector3(size.x,size.y*.5f,size.z),Mat("Product "+i,color));pail.transform.SetParent(root.transform,false);
                var lid=Primitive("Lid",PrimitiveType.Cylinder,new Vector3(0,size.y*.5f+.008f,0),new Vector3(size.x*1.04f,.008f,size.z*1.04f),Mat("Product lid "+i,color*.55f));lid.transform.SetParent(root.transform,false);
                var rim=Primitive("Rim",PrimitiveType.Cylinder,new Vector3(0,size.y*.36f,0),new Vector3(size.x*1.03f,.012f,size.z*1.03f),Mat("Product lid "+i,color*.55f));rim.transform.SetParent(root.transform,false);
            }
            else
            {
                var body=Cube("Package",Vector3.zero,size,Mat("Product "+i,color));body.transform.SetParent(root.transform,false);
            }
            // Label art from scripts/prepare_products.py: a printed front panel, a printed top, and a barcode label.
            // Without those files (the unenrolled package has none) the box keeps a plain placeholder panel.
            float front=-size.z*.5f-.004f;
            float faceWidth=drum?size.x*.62f:size.x*.94f;
            float labelWidth=Mathf.Min(faceWidth,.34f),labelHeight=labelWidth*330f/1110f;
            bool hasBarcode=File.Exists(Root+"/Products/"+p.sku+"_barcode.png");
            float artHeight=size.y*.96f-(hasBarcode?labelHeight+.014f:0f);
            bool printed=Sticker(root,"Front print",Root+"/Products/"+p.sku+"_photo.png",
                new Vector3(0,size.y*.5f-artHeight*.5f-size.y*.02f,front),new Vector2(faceWidth,artHeight),Quaternion.identity);
            if(hasBarcode)Sticker(root,"Barcode label",Root+"/Products/"+p.sku+"_barcode.png",
                new Vector3(0,-size.y*.5f+labelHeight*.5f+.008f,front-.002f),new Vector2(labelWidth,labelHeight),Quaternion.identity);
            // The gate camera looks down on carts, so the top of the package is what it mostly sees.
            float topWidth=drum?size.x*.7f:size.x*.94f,topDepth=drum?size.z*.7f:size.z*.94f;
            Sticker(root,"Top print",Root+"/Products/"+p.sku+"_top.png",new Vector3(0,size.y*.5f+(drum?.018f:.004f),0),new Vector2(topWidth,topDepth),Quaternion.Euler(90,0,0));
            if(!printed)
            {
                var inset=Cube("Package face",new Vector3(0,0,-size.z*.5f-.003f),new Vector3(size.x*.91f,size.y*.82f,.004f),
                    Mat("Product panel "+i,new Color(.045f,.055f,.075f)));inset.transform.SetParent(root.transform,false);
                var label=Text(item.name,new Vector3(0,size.y*.12f,-size.z*.5f-.014f),size.x*.035f,Color.white,Quaternion.identity);
                label.transform.SetParent(root.transform,false);
            }
            var prefab=PrefabUtility.SaveAsPrefabAsset(root,path);UnityEngine.Object.DestroyImmediate(root);return prefab;
        }

        // A flat, unlit, textured rectangle on a box face. Returns false when the texture file is absent.
        static bool Sticker(GameObject root,string name,string texturePath,Vector3 position,Vector2 size,Quaternion rotation)
        {
            if(!File.Exists(texturePath))return false;
            AssetDatabase.ImportAsset(texturePath,ImportAssetOptions.ForceUpdate);
            var importer=(TextureImporter)AssetImporter.GetAtPath(texturePath);
            // Mipmaps and anisotropic filtering keep fine barcode bars legible at a distance.
            importer.mipmapEnabled=true;importer.anisoLevel=8;importer.filterMode=FilterMode.Trilinear;
            importer.textureCompression=TextureImporterCompression.Uncompressed;importer.wrapMode=TextureWrapMode.Clamp;
            importer.npotScale=TextureImporterNPOTScale.None;importer.maxTextureSize=2048;importer.SaveAndReimport();
            var texture=AssetDatabase.LoadAssetAtPath<Texture2D>(texturePath);
            string materialPath=Root+"/Materials/"+Path.GetFileNameWithoutExtension(texturePath)+".mat";
            var material=AssetDatabase.LoadAssetAtPath<Material>(materialPath);
            if(material==null){material=new Material(Shader.Find("Universal Render Pipeline/Unlit"));AssetDatabase.CreateAsset(material,materialPath);}
            material.mainTexture=texture;material.SetTexture("_BaseMap",texture);material.color=Color.white;
            var quad=GameObject.CreatePrimitive(PrimitiveType.Quad);quad.name=name;
            UnityEngine.Object.DestroyImmediate(quad.GetComponent<Collider>());
            quad.GetComponent<Renderer>().sharedMaterial=material;
            quad.transform.SetParent(root.transform,false);
            quad.transform.localPosition=position;quad.transform.localRotation=rotation;quad.transform.localScale=new Vector3(size.x,size.y,1);
            return true;
        }

        static Material Mat(string name,Color color)
        {
            string path=Root+"/Materials/"+name+".mat";
            var existing=AssetDatabase.LoadAssetAtPath<Material>(path);
            if(existing!=null){existing.color=color;return existing;}
            var material=new Material(Shader.Find("Universal Render Pipeline/Lit")){name=name};material.color=color;
            material.SetFloat("_Smoothness",.22f);AssetDatabase.CreateAsset(material,path);return material;
        }

        static GameObject Cube(string name,Vector3 position,Vector3 scale,Material material)=>Primitive(name,PrimitiveType.Cube,position,scale,material);
        static GameObject Primitive(string name,PrimitiveType shape,Vector3 position,Vector3 scale,Material material)
        {
            var go=GameObject.CreatePrimitive(shape);go.name=name;go.transform.position=position;go.transform.localScale=scale;
            go.GetComponent<Renderer>().sharedMaterial=material;return go;
        }
        static GameObject Text(string value,Vector3 position,float size,Color color,Quaternion rotation)
        {
            var go=new GameObject(value,typeof(TextMesh));go.transform.position=position;go.transform.rotation=rotation;
            var text=go.GetComponent<TextMesh>();text.text=value;text.fontSize=64;text.characterSize=size*.4f;
            text.anchor=TextAnchor.MiddleCenter;text.alignment=TextAlignment.Center;text.color=color;
            // The default text material draws through everything in front of it.
            var font=text.font!=null?text.font:Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            string path=Root+"/Materials/Text3D.mat";
            var material=AssetDatabase.LoadAssetAtPath<Material>(path);
            var shader=Shader.Find("ProPass/Text3D");
            if(shader!=null&&font!=null)
            {
                if(material==null){material=new Material(shader){name="Text3D"};AssetDatabase.CreateAsset(material,path);}
                material.shader=shader;material.mainTexture=font.material.mainTexture;
                text.font=font;go.GetComponent<MeshRenderer>().sharedMaterial=material;
            }
            return go;
        }
    }
}
