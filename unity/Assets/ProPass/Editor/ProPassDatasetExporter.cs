using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace ProPass.Editor
{
    public static class ProPassDatasetExporter
    {
        public static bool Running { get; private set; }
        public static int Completed { get; private set; }
        public static int Requested { get; private set; }
        public static string LastError { get; private set; }
        public static string OutputRoot { get; private set; }
        static ProPassSimulation simulation;
        static Camera camera;
        static Light light;
        static RenderTexture target;
        static Texture2D pixels;
        static Material[] masks;
        static Material black;
        static readonly List<GameObject> current = new List<GameObject>();
        static Vector3 originalCameraPosition;
        static Quaternion originalCameraRotation;
        static float originalFov;
        static float originalLightIntensity;
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
            camera=simulation.checkoutCamera;
            light=UnityEngine.Object.FindObjectsByType<Light>(FindObjectsSortMode.None).FirstOrDefault(l=>l.type==LightType.Directional);
            originalCameraPosition=camera.transform.position;originalCameraRotation=camera.transform.rotation;originalFov=camera.fieldOfView;
            originalLightIntensity=light!=null?light.intensity:1;
            originalCustomerPosition=simulation.customer!=null?simulation.customer.position:Vector3.zero;
            trainingCount=train;validationCount=validation;testingCount=test;
            Requested=train+validation+test;Completed=0;LastError=null;OutputRoot=directory;
            target=new RenderTexture(960,540,24,RenderTextureFormat.ARGB32){antiAliasing=1};
            pixels=new Texture2D(960,540,TextureFormat.RGB24,false);
            var shader=Shader.Find("Universal Render Pipeline/Unlit");
            black=new Material(shader){color=Color.black};
            masks=new Material[7];
            for(int i=0;i<7;i++) masks[i]=new Material(shader){color=new Color(((i+1)&1)>0?1:0,((i+1)&2)>0?1:0,((i+1)&4)>0?1:0)};
            foreach(string split in new[]{"train","val","test"})
            {
                Directory.CreateDirectory(Path.Combine(directory,"detection","images",split));
                Directory.CreateDirectory(Path.Combine(directory,"detection","labels",split));
                Directory.CreateDirectory(Path.Combine(directory,"manifests",split));
                for(int i=0;i<5;i++) Directory.CreateDirectory(Path.Combine(directory,"crops",split,"PEX-00"+(i+1)));
            }
            Running=true;EditorApplication.update+=Step;
        }

        static void Step()
        {
            if(!Running)return;
            try
            {
                if(Completed>=Requested){Finish();return;}
                ExportOne();Completed++;
                if(Completed%25==0) File.WriteAllText(Path.Combine(OutputRoot,"export-progress.json"),JsonUtility.ToJson(new Progress{completed=Completed,total=Requested,running=true}));
            }
            catch(Exception error){LastError=error.ToString();Debug.LogException(error);Finish();}
        }

        static void ExportOne()
        {
            string split=Completed<trainingCount?"train":Completed<trainingCount+validationCount?"val":"test";
            int splitIndex=split=="train"?Completed:split=="val"?Completed-trainingCount:Completed-trainingCount-validationCount;
            int seed=(split=="train"?13000:split=="val"?28000:44000)+splitIndex;
            UnityEngine.Random.InitState(seed);
            int count=UnityEngine.Random.Range(1,5);
            bool negative=splitIndex%30==0;
            if(negative)count=0;
            for(int i=0;i<count;i++)
            {
                int classIndex=(splitIndex+i)%5;
                // Unenrolled objects are still merchandise for generic localization.
                if(splitIndex%17==0 && i==0)classIndex=5;
                var product=UnityEngine.Object.Instantiate(simulation.productPrefabs[classIndex]);
                product.GetComponent<ProPassProduct>().AssignInstance();
                float x=count==1?UnityEngine.Random.Range(-1.1f,1.1f):Mathf.Lerp(-1.15f,1.15f,(float)i/(count-1));
                float z=UnityEngine.Random.Range(-3.6f,3.9f);
                product.transform.position=new Vector3(x,UnityEngine.Random.Range(.73f,1.12f),z);
                product.transform.rotation=Quaternion.Euler(UnityEngine.Random.Range(-12f,12f),UnityEngine.Random.Range(-65f,65f),UnityEngine.Random.Range(-10f,10f));
                product.transform.localScale=Vector3.one*UnityEngine.Random.Range(.88f,1.12f);
                current.Add(product);
            }
            if(simulation.customer!=null)simulation.customer.position=new Vector3(UnityEngine.Random.Range(-.8f,.8f),0,UnityEngine.Random.Range(-2.8f,3.8f));
            camera.transform.position=originalCameraPosition+new Vector3(UnityEngine.Random.Range(-.18f,.18f),UnityEngine.Random.Range(-.25f,.25f),UnityEngine.Random.Range(-.25f,.25f));
            camera.transform.LookAt(new Vector3(UnityEngine.Random.Range(-.12f,.12f),.75f,UnityEngine.Random.Range(.1f,.4f)));
            camera.fieldOfView=originalFov+UnityEngine.Random.Range(-2f,2f);
            if(light!=null)light.intensity=UnityEngine.Random.Range(1.15f,2.6f);
            Render();
            var rgb=pixels.GetPixels32();
            string stem="scene_"+splitIndex.ToString("D5");
            File.WriteAllBytes(Path.Combine(OutputRoot,"detection","images",split,stem+".jpg"),pixels.EncodeToJPG(92));

            var renderers=UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None);
            var originalMaterials=renderers.Select(r=>r.sharedMaterials).ToArray();
            Color originalBackground=camera.backgroundColor;
            try
            {
                foreach(var renderer in renderers)
                {
                    var product=renderer.GetComponentInParent<ProPassProduct>();
                    int index=product==null?-1:current.FindIndex(p=>p==product.gameObject);
                    var material=index>=0?masks[index]:black;
                    renderer.sharedMaterials=Enumerable.Repeat(material,Math.Max(1,renderer.sharedMaterials.Length)).ToArray();
                }
                camera.backgroundColor=Color.black;
                Render();
                var ids=pixels.GetPixels32();
                var bounds=Enumerable.Range(0,current.Count).Select(_=>new BoundsPixels()).ToArray();
                for(int y=0;y<540;y++)for(int x=0;x<960;x++)
                {
                    var c=ids[y*960+x];int code=(c.r>127?1:0)|(c.g>127?2:0)|(c.b>127?4:0);
                    if(code>0&&code<=current.Count)bounds[code-1].Include(x,539-y);
                }
                var labels=new List<string>();var annotations=new List<Annotation>();
                pixels.SetPixels32(rgb);pixels.Apply(false);
                for(int i=0;i<current.Count;i++)
                {
                    var box=bounds[i];if(box.count<80||box.maxX<=box.minX||box.maxY<=box.minY)continue;
                    float width=box.maxX-box.minX+1,height=box.maxY-box.minY+1;
                    labels.Add(string.Format(CultureInfo.InvariantCulture,"0 {0:F6} {1:F6} {2:F6} {3:F6}",
                        (box.minX+width*.5f)/960f,(box.minY+height*.5f)/540f,width/960f,height/540f));
                    var product=current[i].GetComponent<ProPassProduct>();
                    annotations.Add(new Annotation{sku=product.sku,physical_id=product.physicalId,class_index=product.classIndex,
                        bbox=new[]{box.minX,box.minY,box.maxX+1,box.maxY+1},visible_pixels=box.count});
                    if(product.classIndex<5 && width*height>300)
                    {
                        int x0=Mathf.Max(0,box.minX-5),x1=Mathf.Min(960,box.maxX+6),y0=Mathf.Max(0,box.minY-5),y1=Mathf.Min(540,box.maxY+6);
                        var crop=new Texture2D(x1-x0,y1-y0,TextureFormat.RGB24,false);
                        crop.SetPixels(pixels.GetPixels(x0,540-y1,x1-x0,y1-y0));crop.Apply(false);
                        File.WriteAllBytes(Path.Combine(OutputRoot,"crops",split,product.sku,stem+"_"+i+".jpg"),crop.EncodeToJPG(95));
                        UnityEngine.Object.DestroyImmediate(crop);
                    }
                }
                File.WriteAllLines(Path.Combine(OutputRoot,"detection","labels",split,stem+".txt"),labels);
                File.WriteAllText(Path.Combine(OutputRoot,"manifests",split,stem+".json"),JsonUtility.ToJson(new SceneAnnotation{seed=seed,split=split,objects=annotations.ToArray()}));
            }
            finally
            {
                camera.backgroundColor=originalBackground;
                for(int i=0;i<renderers.Length;i++)if(renderers[i]!=null)renderers[i].sharedMaterials=originalMaterials[i];
                foreach(var product in current)UnityEngine.Object.DestroyImmediate(product);current.Clear();
            }
        }

        static void Render()
        {
            var originalTarget=camera.targetTexture;var originalActive=RenderTexture.active;
            try{camera.targetTexture=target;camera.Render();RenderTexture.active=target;pixels.ReadPixels(new Rect(0,0,960,540),0,0);pixels.Apply(false);}
            finally{camera.targetTexture=originalTarget;RenderTexture.active=originalActive;}
        }

        static void Finish()
        {
            Running=false;EditorApplication.update-=Step;
            foreach(var product in current)if(product!=null)UnityEngine.Object.DestroyImmediate(product);current.Clear();
            if(camera!=null){camera.transform.position=originalCameraPosition;camera.transform.rotation=originalCameraRotation;camera.fieldOfView=originalFov;}
            if(light!=null)light.intensity=originalLightIntensity;
            if(simulation!=null&&simulation.customer!=null)simulation.customer.position=originalCustomerPosition;
            if(target!=null){target.Release();UnityEngine.Object.DestroyImmediate(target);}if(pixels!=null)UnityEngine.Object.DestroyImmediate(pixels);
            if(masks!=null)foreach(var mask in masks)if(mask!=null)UnityEngine.Object.DestroyImmediate(mask);
            if(black!=null)UnityEngine.Object.DestroyImmediate(black);
            if(!string.IsNullOrEmpty(OutputRoot))File.WriteAllText(Path.Combine(OutputRoot,"export-progress.json"),JsonUtility.ToJson(new Progress{completed=Completed,total=Requested,running=false,error=LastError}));
            Debug.Log("ProPass export completed: "+Completed+"/"+Requested);
        }

        class BoundsPixels
        {
            public int minX=960,minY=540,maxX=-1,maxY=-1,count;
            public void Include(int x,int y){minX=Math.Min(minX,x);maxX=Math.Max(maxX,x);minY=Math.Min(minY,y);maxY=Math.Max(maxY,y);count++;}
        }
        [Serializable]class Annotation{public string sku,physical_id;public int class_index;public int[] bbox;public int visible_pixels;}
        [Serializable]class SceneAnnotation{public int seed;public string split;public Annotation[] objects;}
        [Serializable]class Progress{public int completed,total;public bool running;public string error;}
    }
}
