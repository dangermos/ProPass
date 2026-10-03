"""Evaluate learned perception on held-out synthetic scenes.

Ground-truth manifests enter this offline evaluator only. Runtime imports none
of them. Report both classification on perfect crops and detected-crop results.
"""
from pathlib import Path
import argparse
import json
import time

ROOT = Path(__file__).resolve().parents[1]


def iou(a,b):
    overlap = max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    area_a = max(0,a[2]-a[0])*max(0,a[3]-a[1])
    area_b = max(0,b[2]-b[0])*max(0,b[3]-b[1])
    return overlap/max(area_a+area_b-overlap,1e-9)


def main():
    import cv2
    import numpy as np
    from PIL import Image
    from vision.engine import VisionEngine
    parser = argparse.ArgumentParser()
    parser.add_argument("--split",choices=["val","test"],default="test")
    args = parser.parse_args()
    engine = VisionEngine(ROOT/"catalog.json",ROOT/"models",ROOT/"vision"/"config.json")
    if not engine.status()["ready"]:
        raise RuntimeError(engine.status()["error"])
    torch = engine.torch
    torch.set_num_threads(4)

    def classify(image,boxes):
        tensors = []
        for x1,y1,x2,y2 in boxes:
            # Matches runtime detector-crop padding exactly.
            dx,dy = (x2-x1)*0.025,(y2-y1)*0.025
            crop = image[max(0,int(y1-dy)):min(image.shape[0],int(y2+dy)),
                         max(0,int(x1-dx)):min(image.shape[1],int(x2+dx))]
            if crop.size==0:
                raise ValueError("Empty GT/predicted crop")
            tensors.append(engine.transform(Image.fromarray(crop[:,:,::-1])))
        if not tensors:
            return []
        with torch.inference_mode():
            batch = torch.stack(tensors).to(engine.device)
            features = engine.classifier.avgpool(engine.classifier.features(batch)).flatten(1)
            normalized = torch.nn.functional.normalize(features,dim=1)
            probabilities = (engine.classifier.classifier(features)/engine.temperature).softmax(1)
            distances = 1-(normalized*engine.prototypes[probabilities.argmax(1)]).sum(1)
            scores,indices = probabilities.topk(2,dim=1)
            accepted = ((scores[:,0]>=0.85)&(scores[:,0]-scores[:,1]>=0.2)&
                        (distances<=engine.max_prototype_distance)&(indices[:,0]<len(engine.skus)))
        return [{"sku":engine.skus[int(index)] if int(index)<len(engine.skus) else None,"confidence":float(score),
                 "distance":float(distance),"accepted":bool(accept)}
                for index,score,distance,accept in zip(indices[:,0].cpu(),scores[:,0].cpu(),
                                                     distances.cpu(),accepted.cpu())]

    totals = {"images":0,"gt_merchandise":0,"predicted_merchandise":0,
              "matched_iou50":0,"known_gt_crops":0,"known_gt_top1_correct":0,
              "known_gt_accepted":0,"known_gt_accepted_correct":0,
              "unknown_gt_crops":0,"unknown_gt_rejected":0,
              "known_detected_crops":0,"known_detected_top1_correct":0,
              "known_detected_accepted":0,"known_detected_accepted_correct":0,
              "unknown_detected_crops":0,"unknown_detected_rejected":0,
              "empty_scenes":0,"empty_scenes_with_false_detections":0}
    detailed = []
    times = []
    manifests = sorted((ROOT/"training"/"data"/"manifests"/args.split).glob("*.json"))
    for path in manifests:
        manifest = json.loads(path.read_text())
        image = cv2.imread(str(ROOT/"training"/"data"/"detection"/"images"/args.split/(path.stem+".jpg")))
        objects = manifest["objects"]
        gt_boxes = [obj["bbox"] for obj in objects]
        started = time.perf_counter()
        boxes = engine.detector.predict(image,imgsz=640,conf=0.20,iou=0.65,
                                        device=engine.device,verbose=False)[0].boxes
        pred_boxes = boxes.xyxy.cpu().tolist() if boxes is not None else []
        prediction = classify(image,pred_boxes)
        times.append((time.perf_counter()-started)*1000)
        gt_prediction = classify(image,gt_boxes)
        totals["images"] += 1
        totals["gt_merchandise"] += len(objects)
        totals["predicted_merchandise"] += len(pred_boxes)
        if not objects:
            totals["empty_scenes"] += 1
            totals["empty_scenes_with_false_detections"] += int(bool(pred_boxes))
        for obj,pred in zip(objects,gt_prediction):
            if obj["sku"] == "UNKNOWN":
                totals["unknown_gt_crops"] += 1
                totals["unknown_gt_rejected"] += int(not pred["accepted"])
            else:
                totals["known_gt_crops"] += 1
                correct = pred["sku"]==obj["sku"]
                totals["known_gt_top1_correct"] += int(correct)
                totals["known_gt_accepted"] += int(pred["accepted"])
                totals["known_gt_accepted_correct"] += int(correct and pred["accepted"])
        # One-to-one greedy IoU matching, explicit unmatched errors.
        pairs = sorted([(iou(box,gt),i,j) for i,box in enumerate(pred_boxes)
                        for j,gt in enumerate(gt_boxes)],reverse=True)
        matched_pred,matched_gt,matches = set(),set(),[]
        for score,i,j in pairs:
            if score<0.5:
                break
            if i in matched_pred or j in matched_gt:
                continue
            matched_pred.add(i); matched_gt.add(j)
            totals["matched_iou50"] += 1
            obj,pred = objects[j],prediction[i]
            if obj["sku"]=="UNKNOWN":
                totals["unknown_detected_crops"] += 1
                totals["unknown_detected_rejected"] += int(not pred["accepted"])
            else:
                correct = pred["sku"]==obj["sku"]
                totals["known_detected_crops"] += 1
                totals["known_detected_top1_correct"] += int(correct)
                totals["known_detected_accepted"] += int(pred["accepted"])
                totals["known_detected_accepted_correct"] += int(correct and pred["accepted"])
            matches.append({"iou":score,"gt_sku":obj["sku"],"prediction":pred})
        detailed.append({"scene":path.stem,"matches":matches,
                         "missed":len(objects)-len(matched_gt),
                         "false_detections":len(pred_boxes)-len(matched_pred)})
    report = {"split":args.split,"domain":"Unity synthetic held-out randomized scenes",
              "runtime_ground_truth":False,"operating_threshold":0.20,"totals":totals,
              "latency_ms": {"warmup_excluded":True,
                             "median":float(np.median(times[1:])),
                             "p95":float(np.percentile(times[1:],95))},
              "limitations":["Five visually distinct fictional packages; no real camera transfer tested",
                             "Unknown package sample is small; rejection is not general open-world detection",
                             "Static scenes do not establish temporal exact-cart accuracy"],
              "scenes":detailed}
    output = ROOT/"models"/f"evaluation-static-{args.split}.json"
    output.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="scenes"},indent=2),flush=True)


if __name__=="__main__":
    main()
