using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace ProPass.Editor
{
    // Renders randomized, cluttered checkout scenes with tight, occlusion-aware labels.
    //   Detection labels (YOLO): 0 merchandise · 1 person (shoppers, customer, hands) · 2 cart (flatbed)
    //   Hard negatives: phones, cups and bags appear unlabeled, so they are learned as background.
    //   Crops: one folder per SKU for the classifier, including partially occluded views.
    // Half the scenes are rendered from the overhead camera, half from the lane camera.
    // Labels come from one mask render per instance, so a half-hidden box gets a half-size box.
    public static class ProPassDatasetExporter
    {
        public static readonly string[] ClassNames = { "merchandise", "person", "cart" };
        static readonly int[] Enrolled = { 0, 1, 2, 3, 4, 6, 7, 8 };
        public static bool Running { get; private set; }
        public static int Completed { get; private set; }
        public static int Requested { get; private set; }
        public static string LastError { get; private set; }
        public static string OutputRoot { get; private set; }
        static ProPassSimulation simulation;
        static Camera camera;      // the lane camera saved in the scene
        static Camera overhead;
        static Camera active;      // the camera this scene is rendered from
        static Vector3 overheadPosition;
        static Light light;
        static RenderTexture target;
        static Texture2D pixels;
        static Material white, black;
        static ProPassActorFactory factory;
        static readonly List<GameObject> current = new List<GameObject>();
        static Vector3 originalCameraPosition;
        static Quaternion originalCameraRotation;
        static float originalFov;
        static float originalLightIntensity;
        static Color originalLightColor;
        static Vector3 originalCustomerPosition;
        static int trainingCount;
        static int validationCount;
        static int testingCount;

        public static void Begin(string directory,int train=450,int validation=90,int test=60)
        {
            if(Running) throw new InvalidOperationException("Dataset export already running.");
            if(EditorApplication.isPlaying) throw new InvalidOperationException("Stop Play mode before exporting training data.");
            simulation=UnityEngine.Object.FindFirstObjectByType<ProPassSimulation>();
            if(simulation==null) throw new InvalidOperationException("Build the checkout scene first.");
            if(simulation.occluder!=null) simulation.occluder.gameObject.SetActive(false);
            camera=simulation.checkoutCamera;
            light=UnityEngine.Object.FindObjectsByType<Light>(FindObjectsSortMode.None).FirstOrDefault(l=>l.type==LightType.Directional);
            overhead=ProPassCameras.Ensure(camera)[1];overheadPosition=overhead.transform.position;
            originalCameraPosition=camera.transform.position;originalCameraRotation=camera.transform.rotation;originalFov=camera.fieldOfView;
            originalLightIntensity=light!=null?light.intensity:1;originalLightColor=light!=null?light.color:Color.white;
            originalCustomerPosition=simulation.customer!=null?simulation.customer.position:Vector3.zero;
            trainingCount=train;validationCount=validation;testingCount=test;
            Requested=train+validation+test;Completed=0;LastError=null;OutputRoot=directory;
            target=new RenderTexture(960,540,24,RenderTextureFormat.ARGB32){antiAliasing=1};
            pixels=new Texture2D(960,540,TextureFormat.RGB24,false);
            var shader=Shader.Find("Universal Render Pipeline/Unlit");
            white=new Material(shader){color=Color.white};
            black=new Material(shader){color=Color.black};
            factory=new ProPassActorFactory(simulation.characters);
            foreach(string split in new[]{"train","val","test"})
            {
                Directory.CreateDirectory(Path.Combine(directory,"detection","images",split));
                Directory.CreateDirectory(Path.Combine(directory,"detection","labels",split));
                Directory.CreateDirectory(Path.Combine(directory,"manifests",split));
                foreach(var prefab in simulation.productPrefabs)
                {
                    string sku=prefab.GetComponent<ProPassProduct>().sku;
                    if(sku!="UNKNOWN") Directory.CreateDirectory(Path.Combine(directory,"crops",split,sku));
                }
            }
            Running=true;EditorApplication.update+=Step;
        }

        static void Step()
        {
            if(!Running)return;
            try
            {
                // Several scenes per editor tick keeps the export fast without freezing the Editor.
                for(int i=0;i<4&&Completed<Requested;i++){ExportOne();Completed++;}
                if(Completed>=Requested){Finish();return;}
                if(Completed%24==0) File.WriteAllText(Path.Combine(OutputRoot,"export-progress.json"),JsonUtility.ToJson(new Progress{completed=Completed,total=Requested,running=true}));
            }
            catch(Exception error){LastError=error.ToString();Debug.LogException(error);Finish();}
        }

        static void ExportOne()
        {
            string split=Completed<trainingCount?"train":Completed<trainingCount+validationCount?"val":"test";
            int splitIndex=split=="train"?Completed:split=="val"?Completed-trainingCount:Completed-trainingCount-validationCount;
            int seed=(split=="train"?13000:split=="val"?28000:44000)+splitIndex;
            var rng=new System.Random(seed);
            float R(float a,float b)=>a+(float)rng.NextDouble()*(b-a);
            bool Chance(double p)=>rng.NextDouble()<p;
            var instances=new List<(GameObject go,int cls)>();
            var products=new List<GameObject>();

            int count=rng.Next(1,5);
            if(splitIndex%30==0)count=0;
            for(int i=0;i<count;i++)
            {
                // Every enrolled product in turn; prefab 5 is the unenrolled package.
                int classIndex=Enrolled[(splitIndex+i)%Enrolled.Length];
                // Unenrolled objects are still merchandise for generic localization.
                if(splitIndex%17==0 && i==0)classIndex=5;
                float x=count==1?R(-1.45f,1.45f):Mathf.Lerp(-1.4f,1.4f,(float)i/(count-1))+R(-.12f,.12f);
                // z down to -5 places some packages partly below the frame edge.
                var product=Product(classIndex,new Vector3(x,R(.65f,1.2f),R(-5f,3.9f)),rng);
                products.Add(product);instances.Add((product,0));
            }
            if(products.Count>0&&Chance(.25))
            {
                var bottom=products[rng.Next(products.Count)];
                var top=Product(rng.Next(5),bottom.transform.position+new Vector3(R(-.06f,.06f),R(.4f,.5f),R(-.04f,.04f)),rng);
                products.Add(top);instances.Add((top,0));
            }
            if(simulation.customer!=null)
            {
                simulation.customer.position=new Vector3(R(-.8f,.8f),0,R(-2.8f,3.8f));
                // An animated character stands in for the capsule customer when the pack is present.
                var customer=factory.CustomerAvatar(simulation.customer,seed);
                if(customer!=null)factory.Pose(customer,simulation.customer.position,Chance(.7)?new Vector3(R(-.2f,.2f),0,R(.4f,1.2f)*(Chance(.85)?1:-1)):Vector3.zero,R(0,20),R(-40,40));
                instances.Add((customer??simulation.customer.gameObject,1));
            }
            if(Chance(.35))
            {
                var shopper=factory.Shopper(Color.HSVToRGB(R(0,1),R(.3f,.8f),R(.35f,.85f)),rng.Next(1024));
                float heading=R(0,360);var where=new Vector3(R(-3.3f,3.3f),0,R(-3.5f,4f));
                Place(shopper,where,heading);
                // Characters walk or stand facing their heading; capsules are simply placed.
                factory.Pose(shopper,where,Chance(.7)?Quaternion.Euler(0,heading,0)*Vector3.forward*R(.5f,1.3f):Vector3.zero,R(0,20),heading);
                instances.Add((shopper,1));
            }
            if(products.Count>0&&Chance(.35))
            {
                var near=products[rng.Next(products.Count)].transform.position;
                instances.Add((Place(factory.Arm(new Color(.08f,.1f,.14f)*R(.8f,2.5f)),near+new Vector3(R(-.2f,.2f),R(.1f,.25f),R(-.35f,-.2f)),R(-40,40)),1));
            }
            if(Chance(.2)) instances.Add((Place(factory.Flatbed(new Color(.82f,.68f,.46f)*R(.85f,1.1f)),new Vector3(R(-2.5f,2.5f),0,R(-3.5f,3f)),R(-15,15)),2));
            foreach(var prop in new[]{"phone","cup","bag"})
            {
                if(!Chance(.3))continue;
                var anchor=products.Count>0?products[rng.Next(products.Count)].transform.position:new Vector3(R(-1.2f,1.2f),.9f,R(-3f,3.5f));
                var color=prop=="bag"?new Color(.45f,.36f,.26f)*R(.7f,1.4f):prop=="cup"?new Color(.92f,.92f,.9f):new Color(.05f,.05f,.06f);
                Place(factory.Prop(prop,color),anchor+new Vector3(R(-.8f,.8f),prop=="bag"?R(-.4f,-.2f):R(-.05f,.2f),R(-.4f,.4f)),R(0,360));
            }

            // Half the scenes are seen from the overhead camera, so both models learn both views.
            active=Chance(.5)?overhead:camera;
            if(active==overhead)
            {
                overhead.transform.position=overheadPosition+new Vector3(R(-.2f,.2f),R(-.25f,.25f),R(-.2f,.2f));
                overhead.fieldOfView=50f+R(-2f,2f);
            }
            else
            {
                camera.transform.position=originalCameraPosition+new Vector3(R(-.18f,.18f),R(-.25f,.25f),R(-.25f,.25f));
                camera.transform.LookAt(new Vector3(R(-.12f,.12f),.75f,R(.1f,.4f)));
                camera.fieldOfView=originalFov+R(-2f,2f);
            }
            if(light!=null){light.intensity=R(1.15f,2.6f);light.color=Color.Lerp(Color.white,new Color(1f,.86f,.7f),R(0,.6f));}
            Render();
            var rgb=pixels.GetPixels32();
            string stem="scene_"+splitIndex.ToString("D5");
            File.WriteAllBytes(Path.Combine(OutputRoot,"detection","images",split,stem+".jpg"),pixels.EncodeToJPG(rng.Next(72,95)));

            var renderers=UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None);
            var originalMaterials=renderers.Select(r=>r.sharedMaterials).ToArray();
            Color originalBackground=active.backgroundColor;
            try
            {
                active.backgroundColor=Color.black;
                var bounds=new BoundsPixels[instances.Count];
                for(int k=0;k<instances.Count;k++)
                {
                    var mine=new HashSet<Renderer>(instances[k].go.GetComponentsInChildren<Renderer>());
                    foreach(var renderer in renderers)
                        renderer.sharedMaterials=Enumerable.Repeat(mine.Contains(renderer)?white:black,Math.Max(1,renderer.sharedMaterials.Length)).ToArray();
                    Render();
                    var mask=pixels.GetPixels32();var box=new BoundsPixels();
                    for(int y=0;y<540;y++)for(int x=0;x<960;x++)if(mask[y*960+x].r>127)box.Include(x,539-y);
                    bounds[k]=box;
                }
                var labels=new List<string>();var annotations=new List<Annotation>();var others=new List<Other>();
                pixels.SetPixels32(rgb);pixels.Apply(false);
                for(int k=0;k<instances.Count;k++)
                {
                    var box=bounds[k];int cls=instances[k].cls;
                    if(box.count<80||box.maxX<=box.minX||box.maxY<=box.minY)continue;
                    float width=box.maxX-box.minX+1,height=box.maxY-box.minY+1;
                    labels.Add(string.Format(CultureInfo.InvariantCulture,"{0} {1:F6} {2:F6} {3:F6} {4:F6}",
                        cls,(box.minX+width*.5f)/960f,(box.minY+height*.5f)/540f,width/960f,height/540f));
                    var bbox=new[]{box.minX,box.minY,box.maxX+1,box.maxY+1};
                    if(cls!=0){others.Add(new Other{label=ClassNames[cls],bbox=bbox,visible_pixels=box.count});continue;}
                    var product=instances[k].go.GetComponent<ProPassProduct>();
                    annotations.Add(new Annotation{sku=product.sku,physical_id=product.physicalId,class_index=product.classIndex,bbox=bbox,visible_pixels=box.count});
                    if(product.sku!="UNKNOWN" && width*height>300)
                    {
                        int x0=Mathf.Max(0,box.minX-5),x1=Mathf.Min(960,box.maxX+6),y0=Mathf.Max(0,box.minY-5),y1=Mathf.Min(540,box.maxY+6);
                        var crop=new Texture2D(x1-x0,y1-y0,TextureFormat.RGB24,false);
                        crop.SetPixels(pixels.GetPixels(x0,540-y1,x1-x0,y1-y0));crop.Apply(false);
                        File.WriteAllBytes(Path.Combine(OutputRoot,"crops",split,product.sku,stem+"_"+k+".jpg"),crop.EncodeToJPG(95));
                        UnityEngine.Object.DestroyImmediate(crop);
                    }
                }
                File.WriteAllLines(Path.Combine(OutputRoot,"detection","labels",split,stem+".txt"),labels);
                File.WriteAllText(Path.Combine(OutputRoot,"manifests",split,stem+".json"),JsonUtility.ToJson(new SceneAnnotation{seed=seed,split=split,camera=active==overhead?"overhead":"lane",objects=annotations.ToArray(),others=others.ToArray()}));
            }
            finally
            {
                active.backgroundColor=originalBackground;
                for(int i=0;i<renderers.Length;i++)if(renderers[i]!=null)renderers[i].sharedMaterials=originalMaterials[i];
                foreach(var go in current)if(go!=null)UnityEngine.Object.DestroyImmediate(go);current.Clear();
                factory.DisposeCharacters();
            }
        }

        static GameObject Product(int classIndex,Vector3 position,System.Random rng)
        {
            float R(float a,float b)=>a+(float)rng.NextDouble()*(b-a);
            var product=UnityEngine.Object.Instantiate(simulation.productPrefabs[classIndex]);
            product.GetComponent<ProPassProduct>().AssignInstance();
            product.transform.position=position;
            product.transform.rotation=Quaternion.Euler(R(-12f,12f),R(-65f,65f),R(-10f,10f));
            product.transform.localScale=Vector3.one*R(.88f,1.12f);
            current.Add(product);
            return product;
        }

        static GameObject Place(GameObject go,Vector3 position,float yaw)
        {
            go.transform.SetPositionAndRotation(position,Quaternion.Euler(0,yaw,0));
            current.Add(go);
            return go;
        }

        static void Render()
        {
            var originalTarget=active.targetTexture;var originalActive=RenderTexture.active;
            try{active.targetTexture=target;active.Render();RenderTexture.active=target;pixels.ReadPixels(new Rect(0,0,960,540),0,0);pixels.Apply(false);}
            finally{active.targetTexture=originalTarget;RenderTexture.active=originalActive;}
        }

        static void Finish()
        {
            Running=false;EditorApplication.update-=Step;
            foreach(var go in current)if(go!=null)UnityEngine.Object.DestroyImmediate(go);current.Clear();
            if(camera!=null){camera.transform.position=originalCameraPosition;camera.transform.rotation=originalCameraRotation;camera.fieldOfView=originalFov;}
            if(light!=null){light.intensity=originalLightIntensity;light.color=originalLightColor;}
            if(simulation!=null&&simulation.customer!=null)simulation.customer.position=originalCustomerPosition;
            if(target!=null){target.Release();UnityEngine.Object.DestroyImmediate(target);}if(pixels!=null)UnityEngine.Object.DestroyImmediate(pixels);
            if(white!=null)UnityEngine.Object.DestroyImmediate(white);
            if(black!=null)UnityEngine.Object.DestroyImmediate(black);
            factory?.Dispose();factory=null;
            ProPassCameras.Release();
            if(!string.IsNullOrEmpty(OutputRoot))File.WriteAllText(Path.Combine(OutputRoot,"export-progress.json"),JsonUtility.ToJson(new Progress{completed=Completed,total=Requested,running=false,error=LastError}));
            Debug.Log("ProPass export completed: "+Completed+"/"+Requested);
        }

        class BoundsPixels
        {
            public int minX=960,minY=540,maxX=-1,maxY=-1,count;
            public void Include(int x,int y){minX=Math.Min(minX,x);maxX=Math.Max(maxX,x);minY=Math.Min(minY,y);maxY=Math.Max(maxY,y);count++;}
        }
        [Serializable]class Annotation{public string sku,physical_id;public int class_index;public int[] bbox;public int visible_pixels;}
        [Serializable]class Other{public string label;public int[] bbox;public int visible_pixels;}
        [Serializable]class SceneAnnotation{public int seed;public string split,camera;public Annotation[] objects;public Other[] others;}
        [Serializable]class Progress{public int completed,total;public bool running;public string error;}
    }
}
