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
        static readonly Color[] Colors = { new Color(.93f,.24f,.18f), new Color(.08f,.58f,.72f),
            new Color(.96f,.71f,.12f), new Color(.38f,.27f,.72f), new Color(.24f,.64f,.35f), new Color(.6f,.59f,.56f),
            new Color(.16f,.18f,.22f), new Color(.86f,.74f,.52f), new Color(.45f,.5f,.3f) };
        // Prefab order: five boxed products, the unenrolled package, a locked-cage tool, then lumber
        // (plain and pressure-treated). Skus and ClassIndex must match catalog.json.
        static readonly string[] Names = { "DRILL KIT", "DRIVER KIT", "MEASURING TAPE", "FASTENERS", "WORK GLOVES", "UNENROLLED",
            "ROTARY HAMMER", "2x4 STUD", "2x4 TREATED" };
        static readonly string[] Skus = { "PEX-001", "PEX-002", "PEX-003", "PEX-004", "PEX-005", "UNKNOWN", "PEX-006", "PEX-007", "PEX-008" };
        static readonly int[] ClassIndex = { 0, 1, 2, 3, 4, -1, 5, 6, 7 };
        static readonly Vector3[] Sizes = { new Vector3(.67f,.48f,.39f),new Vector3(.61f,.45f,.34f),
            new Vector3(.36f,.34f,.18f),new Vector3(.45f,.36f,.29f),new Vector3(.45f,.4f,.2f),new Vector3(.52f,.4f,.3f),
            new Vector3(.58f,.42f,.3f),new Vector3(.09f,.04f,1.2f),new Vector3(.09f,.04f,1.2f) };

        [MenuItem("ProPass/Build checkout scene")]
        public static void Build()
        {
            Directory.CreateDirectory(Root + "/Scenes");
            Directory.CreateDirectory(Root + "/Prefabs");
            Directory.CreateDirectory(Root + "/Materials");
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var floor = Mat("Floor", new Color(.12f,.15f,.19f));
            var dark = Mat("Fixtures", new Color(.08f,.1f,.14f));
            var steel = Mat("Steel", new Color(.27f,.32f,.37f));
            var orange = Mat("Signal orange", new Color(1f,.36f,.12f));
            var teal = Mat("Signal teal", new Color(.04f,.75f,.65f));
            var white = Mat("Off white", new Color(.88f,.9f,.89f));
            Cube("Warehouse floor", new Vector3(0,-.15f,0), new Vector3(14,.3f,15), floor);
            Cube("Checkout passage", new Vector3(0,.008f,0),new Vector3(3.2f,.015f,12),steel);
            for(int side=-1;side<=1;side+=2)
            {
                for(int z=-3;z<=4;z+=2)
                {
                    Cube("Shelf upright",new Vector3(side*4f,1.2f,z),new Vector3(.12f,2.4f,.15f),orange);
                    for(int level=0;level<3;level++)
                    {
                        Cube("Shelf bay",new Vector3(side*4f,.4f+level*.75f,z+.55f),new Vector3(1.4f,.08f,1.5f),steel);
                        for(int k=0;k<3;k++) Cube("Background stock",new Vector3(side*4f+(k-1)*.37f,.62f+level*.75f,z+.55f),
                            new Vector3(.27f,.35f,.3f),k%2==0?dark:white);
                    }
                }
                Cube("Lane rail",new Vector3(side*1.68f,.2f,0),new Vector3(.08f,.4f,10),dark);
                Cube("Lane light",new Vector3(side*1.72f,.42f,0),new Vector3(.035f,.035f,10),teal);
            }
            Cube("Approach marker",new Vector3(0,.03f,-2),new Vector3(3.1f,.025f,.09f),orange);
            Cube("Commit marker",new Vector3(0,.035f,1.6f),new Vector3(3.1f,.025f,.09f),teal);
            for(int i=0;i<5;i++) Cube("Directional marker",new Vector3(0,.026f,-3+i*1.35f),new Vector3(.04f,.012f,.4f),white);
            Cube("Portal left",new Vector3(-1.9f,1.65f,2),new Vector3(.2f,3.3f,.3f),orange);
            Cube("Portal right",new Vector3(1.9f,1.65f,2),new Vector3(.2f,3.3f,.3f),orange);
            Cube("Portal header",new Vector3(0,3.2f,2),new Vector3(4,.35f,.3f),dark);
            Text("PROPASS",new Vector3(0,3.2f,1.82f),.2f,Color.white,Quaternion.identity);

            var cameraObject = new GameObject("Checkout Camera",typeof(Camera),typeof(UniversalAdditionalCameraData));
            cameraObject.tag="MainCamera";
            var camera=cameraObject.GetComponent<Camera>();
            camera.transform.position=new Vector3(0,7.5f,-8f);
            camera.transform.LookAt(new Vector3(0,.75f,.25f));
            camera.fieldOfView=49;
            camera.nearClipPlane=.05f; camera.farClipPlane=60;
            camera.clearFlags=CameraClearFlags.SolidColor; camera.backgroundColor=new Color(.055f,.073f,.098f);
            camera.allowHDR=false; camera.allowMSAA=false;
            cameraObject.GetComponent<UniversalAdditionalCameraData>().renderPostProcessing=false;
            var lightObject=new GameObject("Key daylight",typeof(Light));
            var light=lightObject.GetComponent<Light>();light.type=LightType.Directional;light.intensity=2.1f;
            light.transform.rotation=Quaternion.Euler(48,-28,0); light.shadows=LightShadows.Soft;
            RenderSettings.ambientMode=AmbientMode.Flat;RenderSettings.ambientLight=new Color(.48f,.5f,.54f);

            var simulator=new GameObject("ProPass Simulation").AddComponent<ProPassSimulation>();
            simulator.checkoutCamera=camera;
            simulator.productPrefabs=new GameObject[Skus.Length];
            for(int i=0;i<Skus.Length;i++) simulator.productPrefabs[i]=Product(i);
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
            var occluder=Cube("Temporary hand occluder",new Vector3(0,1,0),new Vector3(.88f,.9f,.18f),dark);
            occluder.SetActive(false);simulator.occluder=occluder.transform;
            EditorSceneManager.SaveScene(scene,Root+"/Scenes/Checkout.unity");
            EditorBuildSettings.scenes=new[]{new EditorBuildSettingsScene(Root+"/Scenes/Checkout.unity",true)};
            AssetDatabase.SaveAssets();
            Selection.activeGameObject=simulator.gameObject;
        }

        static GameObject Product(int i)
        {
            var root=new GameObject("Product "+Names[i]);
            var p=root.AddComponent<ProPassProduct>();p.sku=Skus[i];
            p.classIndex=ClassIndex[i];p.brandColor=Colors[i];p.packageSize=Sizes[i];
            if(Sizes[i].z>1f)
            {
                // Lumber: a bare board with darker end grain, no packaging and no barcode.
                var board=Cube("Board",Vector3.zero,Sizes[i],Mat("Product "+i,Colors[i]));board.transform.SetParent(root.transform,false);
                for(int end=-1;end<=1;end+=2)
                {
                    var grain=Cube("End grain",new Vector3(0,0,end*(Sizes[i].z*.5f+.002f)),new Vector3(Sizes[i].x,Sizes[i].y,.004f),Mat("Product grain "+i,Colors[i]*.7f));
                    grain.transform.SetParent(root.transform,false);
                }
                var boardPrefab=PrefabUtility.SaveAsPrefabAsset(root,Root+"/Prefabs/Product"+i+".prefab");UnityEngine.Object.DestroyImmediate(root);return boardPrefab;
            }
            var body=Cube("Package",Vector3.zero,Sizes[i],Mat("Product "+i,Colors[i]));body.transform.SetParent(root.transform,false);
            var inset=Cube("Package face",new Vector3(0,0,-Sizes[i].z*.5f-.003f),new Vector3(Sizes[i].x*.91f,Sizes[i].y*.82f,.004f),
                Mat("Product panel "+i,new Color(.045f,.055f,.075f)));inset.transform.SetParent(root.transform,false);
            var stripe=Cube("Brand stripe",new Vector3(0,Sizes[i].y*.27f,-Sizes[i].z*.5f-.01f),new Vector3(Sizes[i].x*.9f,.03f,.004f),
                Mat("Product stripe "+i,Colors[i]));stripe.transform.SetParent(root.transform,false);
            var brand=Text("WORKSHOP",new Vector3(0,Sizes[i].y*.11f,-Sizes[i].z*.5f-.014f),Sizes[i].x*.052f,Color.white,Quaternion.identity);
            brand.transform.SetParent(root.transform,false);
            var label=Text(Names[i],new Vector3(0,-Sizes[i].y*.04f,-Sizes[i].z*.5f-.014f),Sizes[i].x*.035f,Color.white,Quaternion.identity);
            label.transform.SetParent(root.transform,false);
            var model=Text(i<5?"MODEL "+(i+1)+" / DEMO":i==6?"LOCKED CASE":"UNENROLLED",new Vector3(0,-Sizes[i].y*.22f,-Sizes[i].z*.5f-.014f),Sizes[i].x*.027f,Colors[i],Quaternion.identity);
            model.transform.SetParent(root.transform,false);
            // Real-life dressing from scripts/prepare_products.py: a barcode label on the front face, and the
            // product photo when the owner supplied one. Without those files the box keeps its placeholder art.
            float front=-Sizes[i].z*.5f-.016f;
            float labelWidth=Mathf.Min(Sizes[i].x*.9f,.34f),labelHeight=labelWidth*330f/1110f;
            bool labelled=Sticker(root,"Barcode label",Root+"/Products/"+p.sku+"_barcode.png",
                new Vector3(0,-Sizes[i].y*.5f+labelHeight*.5f+.012f,front),new Vector2(labelWidth,labelHeight));
            float photoHeight=Sizes[i].y-(labelled?labelHeight+.035f:.03f);
            float photoWidth=Mathf.Min(Sizes[i].x*.92f,photoHeight*1.3f);
            if(Sticker(root,"Product photo",Root+"/Products/"+p.sku+"_photo.png",
                new Vector3(0,Sizes[i].y*.5f-photoHeight*.5f-.012f,front),new Vector2(photoWidth,photoWidth/1.3f)))
            {
                UnityEngine.Object.DestroyImmediate(brand);UnityEngine.Object.DestroyImmediate(label);
                UnityEngine.Object.DestroyImmediate(model);UnityEngine.Object.DestroyImmediate(stripe);
            }
            else if(labelled)
            {
                // Keep the placeholder text clear of the label.
                foreach(var text in new[]{brand,label,model,stripe})text.transform.localPosition+=new Vector3(0,labelHeight*.5f,0);
            }
            string path=Root+"/Prefabs/Product"+i+".prefab";
            var prefab=PrefabUtility.SaveAsPrefabAsset(root,path);UnityEngine.Object.DestroyImmediate(root);return prefab;
        }

        // A flat, unlit, textured rectangle on a box face. Returns false when the texture file is absent.
        static bool Sticker(GameObject root,string name,string texturePath,Vector3 position,Vector2 size)
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
            quad.transform.localPosition=position;quad.transform.localScale=new Vector3(size.x,size.y,1);
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
            text.anchor=TextAnchor.MiddleCenter;text.alignment=TextAlignment.Center;text.color=color;return go;
        }
    }
}
