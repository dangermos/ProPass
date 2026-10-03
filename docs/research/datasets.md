# Pro Express: dataset and footage research

Researched October 2, 2026. This report distinguishes published dataset facts from engineering recommendations. “Unknown” means not established from the inspected primary source; it is not a claim that the information does not exist. Download sizes are source-reported unless explicitly marked estimates. No large dataset downloads were performed, so links can be identified without guaranteeing successful transfer.

## Recommendation and ranking

**Build a small staged, self-recorded checkout-zone dataset using the exact physical products and camera geometry of the demo.** Public datasets provide useful benchmarks and techniques, but no verified public source supplies Home Depot hardware SKUs, persistent handheld-product identities, customer ownership, and checkout events together. A detector trained on grocery shelves does not automatically recognize a boxed drill, and a video anomaly label is not transaction ground truth.

Ranked for Pro Express: (1) self-recorded 5–8 SKU MVP, then 10–20 SKU extension; (2) Grocery Vision 2023 for cart add/remove and exact-product retrieval, if access arrives; (3) ARC/AI City 2023 Track 4 for one-camera product counting methods and synthetic-to-real evaluation; (4) RPC for cluttered exact-product detection/counting; (5) RetailAction for real overhead shelf Take/Put/Touch interactions; (6) D2S for instance segmentation and copy-paste augmentation; (7) Unitail-OCR for packaging text; (8) RP2K/Products-10K for retrieval pretraining; (9) SKU110K for generic dense merchandise boxes; (10) EPIC VISOR for hand-object contact and temporal segmentation. The rest below are research leads or stress-test data, not primary MVP training data.

The strongest combination is **self-recorded detector/recognizer training + self-recorded fully held-out transaction videos + ARC/RPC methods as external baselines**. The second-week extension can use Grocery Vision for cart interactions or RetailAction for shelf events. Avoid merging all datasets into one training set indiscriminately: their class definitions, camera views, rights, and tasks differ.

## Comparison: all 17 requested fields

The three aligned tables collectively contain: name, URL, type, count, resolution, perspective, annotations, product annotations, tracking IDs, person IDs, hand/object interaction labels, licensing, publication restrictions, approximate download size, training suitability, public GitHub suitability, and Pro Express usefulness. “No” means that label type is not supplied by the published description, not that the imagery contains no such objects. Dataset product IDs are not automatically Home Depot SKU IDs.

### Table A: source, scale, imaging, annotations (fields 1–7 and 14)

| ID / Name / source URL | Type and published count | Resolution / camera perspective | Core annotations | Approximate download size |
|--- |--- |--- |--- |--- |
| 1. Self-recorded Pro Express | Proposed 60 short clips MVP, 120–180 extension; exact owned/borrowed products | 1920×1080, 30 fps; fixed elevated oblique camera; optional opposite side camera | Boxes, physical instance IDs, SKU, session/customer pseudonym, event timestamps, final cart; chosen by developer | Estimate: 10–30 min at 8–20 Mbps ≈0.6–4.5 GB per camera, plus images |
| 2. [Grocery Vision 2023 / PRAW](https://physicalstoreworkshop.github.io/challenge.html) | TAL/STAL 73,683 image-annotation pairs; ABV 74,200 product images | Cart-mounted GoPro in grocery stores; image dimensions not stated on challenge page | Add/remove basket actions, temporal/spatial action localization; ABV filenames carry product barcodes | Unknown; affiliation-email request required |
| 3. [ARC / AI City 2023 Track 4](https://www.aicitychallenge.org/2023-data-and-evaluation/) | 116,500 synthetic images; 116 merchandise assets; [authors report ~22 min real video](https://arxiv.org/html/2308.09708v1); exact clip count unknown | Synthetic variable camera pose; real top-down camera above white checkout tray; exact released-video dimensions not established here | Synthetic class and segmentation labels; evaluated once-per-item recognition time/frame within ROI | Unknown; [current official access page](https://www.aicitychallenge.org/ai-city-challenge-dataset-access/) and [download page](https://www.aicitychallenge.org/2023-track4-download/) |
| 4. [RPC](https://rpc-dataset.github.io/) / [paper](https://arxiv.org/abs/1901.07249) | 83,739 images: 53,739 exemplars +30,000 checkout images; 200 products | Exemplars 2592×1944, checkout 1800×1800; multi-view turntable and top-down whiteboard ([benchmark paper](https://isrc.iscas.ac.cn/zhanglibo/pdfs/2019/ACMMM_2019.pdf)) | Product category and boxes; checkout quantity/shopping-list task | Project page: ~15 GB |
| 5. [RetailAction](https://huggingface.co/datasets/standard-cognition/RetailAction) / [paper](https://openaccess.thecvf.com/content/ICCV2025W/RetailVision/papers/Mazzini_RetailAction_Dataset_for_Multi-View_Spatio-Temporal_Localization_of_Human-Object_Interactions_in_ICCVW_2025_paper.pdf) | 21,000 two-view samples; publisher reports ~41 h and >10,000 shoppers /10 stores | Source cameras 2880×2880, 30 fps, ceiling ≈2.5 m; released clips cropped and motion-subsampled to ≤32 frames (not dense 30 fps video) | Take/Put/Touch intervals and interaction points; subject pose and face locations, timestamps | HF repository: 31.9 GB |
| 6. [MVTec D2S](https://www.mvtec.com/research-teaching/datasets/mvtec-d2s) / [paper](https://openaccess.thecvf.com/content_ECCV_2018/papers/Patrick_Follmann_D2S_Densely_Segmented_ECCV_2018_paper.pdf) | 21,000 images, 60 classes; 4,380 train/3,600 validation/13,020 test | 1920×1440; controlled top-down industrial checkout, rotations/light/background changes | Pixel-precise instance masks/boxes; test annotations withheld | Official page does not establish total archive size; reserve several GB, verify actual archive |
| 7. [SKU110K](https://github.com/eg4000/SKU110K_CVPR19) | 11,743 official fixed-split images; >1.7M boxes; 8,219 train/588 val/2,936 test | Variable high-resolution store shelf images; primarily frontal/oblique dense shelves | One generic merchandise box class; not 110k SKU classes | Distribution-dependent roughly 13–17 GB; do not quote one format as universal |
| 8. [Unitail](https://unitedretail.github.io/) / [paper](https://arxiv.org/abs/2204.00298) | Det: 1.8M quadrilateral instances; OCR: 1,454 product categories, 30k text regions, 21k transcriptions | Real shelf imagery + product gallery; variable image sizes, not stated consistently | Quadrilateral detection; product text boxes and transcriptions; matching | Unknown; Det access restricted since June 2024, contact author; OCR links remain |
| 9. [RP2K](https://arxiv.org/abs/2006.12634) / [original project](https://www.pinlandata.com/rp2k_dataset) | >500,000 product images; 2,000 products | Variable-size real shelf crops, natural lighting | Product identity + size/shape/flavor/scent attributes | Unknown; original site did not load during research; mirrors require provenance checks |
| 10. [Products-10K](https://products-10k.github.io/) / [paper](https://arxiv.org/html/2008.10545v1) | Paper: nearly 150,000 images; 10,000 SKU-level products | Variable catalog and customer photos from JD.com | Expert-checked image-level SKU labels/hierarchy | Unknown on inspected primary pages |
| 11. [MERL Shopping](https://www.merl.com/research/highlights/merl-shopping-dataset) | Released page: 106 videos ≈2 min each; 41 subjects in [mirrored release README](https://github.com/quental96/merl-shopping/blob/master/ORIGINAL.md), not independently archive-verified; older paper reports 96/32, so use release version | Overhead static lab grocery shelf; release documentation 920×680 at 30 fps | Five temporal shopping action classes | Unknown; official historical FTP address on project page; availability not transfer-tested |
| 12. [GroZi-120](https://cseweb.ucsd.edu/~echristiansen/papers/CVAVI_07.pdf) / [historical project](https://grozi.calit2.net/) | 120 products; paper average 5.6 exemplar images/product; 29 shelf videos | 720×480 mobile shelf video; web exemplars | Product exemplars and in-situ product localization annotations; inspect release variant | Unknown; historical project timed out |
| 13. [Freiburg Groceries](https://github.com/PhilJd/freiburg_groceries_dataset) | 5,000 images, 25 food categories | 256×256; real stores/apartments, varied lighting and views | Image-level category and supplied splits | Unknown; small image dataset |
| 14. [Grocery Store Dataset](https://github.com/marcusklasson/GroceryStoreDataset) | 5,125 natural images; 81 fine-grained/42 coarse classes; iconic image/text per fine class | Smartphone object-centric grocery photos; actual dimensions inspect repository | Fine/coarse class, iconic reference and description | Unknown; directly in repository |
| 15. [Amazon Berkeley Objects](https://amazon-berkeley-objects.s3.amazonaws.com/index.html) / [Amazon Science](https://www.amazon.science/code-and-datasets/amazon-berkeley-objects-abo-dataset) | 147,702 listings, 398,212 catalog images; 8,222 spin products; 7,953 models | Variable originals; small images max 256 px; isolated spin views; synthetic renderable 3D | Product metadata, 3D geometry/materials; some benchmark renders have masks/depth/normals | Small 3 GB; original 110 GB; spins 40 GB; models 154 GB; select assets rather than all |
| 16. [EPIC-KITCHENS-100](https://epic-kitchens.github.io/2025) + [VISOR](https://epic-kitchens.github.io/VISOR/) | 100 h/700 kitchen videos; VISOR 36 h/179 videos, 272k manual masks, 67k hand-object relations | Egocentric home kitchen; largely 1920×1080 / 50 fps; verify video component | Action intervals/nouns/verbs; VISOR active-object and hand masks/contact; automatic boxes are pseudo-labels | Complete published sequence bundles 1.1 TB +740 GB; download specific videos; auto annotation bundle ~10 GB |
| 17. [PRISM-100K](https://huggingface.co/datasets/DreamVu/PRISM-100K) | 100,000 VLM QA samples, 25,173 unique clips; publisher claims quality validated by Gemini | 480p MP4, 4 fps; ego/exo retail | 21 task types; chat-format QA, including hand interaction/object permanence; partly AI-generated | HF reported repository 772 GB; use selected clips, inspect large metadata files |
| 18. [UCF-Crime](https://www.crcv.ucf.edu/research/real-world-anomaly-detection-in-surveillance-videos/) | 1,900 surveillance videos, 128 h, 13 anomaly types plus normal; shoplifting subset | Mixed CCTV/video provenance; varying low resolutions; not one consistent camera | Video-level anomaly training labels, temporal test labels | Official page links large ZIP; bytes not established here |
| 19. [MNNIT Shoplifting 2022](https://data.mendeley.com/datasets/r3yjf35hzr/1) | Lab-recorded staged videos; exact count not exposed in inspected page | 640×480, 30 fps; lab scene captured with 32 MP camera | Normal/shoplifting classes | Unknown |
| 20. [Kaggle Shoplifting Video](https://www.kaggle.com/datasets/kipshidze/shoplifting-video-dataset) and [DCSASS](https://www.kaggle.com/datasets/mateohervas/dcsass-dataset) | Existence verified; cards did not expose content to browser; counts not independently confirmed | Retail/CCTV footage or derived clips, verify individually | Uploader-dependent; typically action classes, not SKU transaction labels | Unknown |
| 21. [PoseLift](https://github.com/TeCSAR-UNCC/PoseLift) / [RetailS](https://github.com/TeCSAR-UNCC/RetailS) | PoseLift 153 sequences; RetailS nearly 20M normal frames | **Pose data, not raw RGB release**; source 6 indoor cameras; PoseLift source 1080p / 15 fps | Person boxes, IDs, COCO pose, frame anomaly labels | Unknown; download links in repos |
| 22. [Simuletic synthetic CCTV sample](https://simuletic.com/blog/cctv-shoplifting-dataset) | Publisher: 400 frames/8 video free sample; full paid 5,000+ frames / 100+ videos | Rendered overhead/oblique retail; resolution not stated | Person boxes, 17-point pose, VLM captions | Unknown; sample linked on Kaggle |
| 23. [POLIMI-ITW-S](https://airlab.deib.polimi.it/polimi-itw-s-a-shopping-mall-dataset-in-the-wild/) | 22,164 video samples/37 action classes | Real shopping mall; fixed cameras; resolution inspect release | RGB, 2D skeleton, boxes, action class | Unknown |
| 24. [LoCount official announcement](https://isrc.iscas.ac.cn/news/20210412-data-set/) / [paper](https://arxiv.org/abs/2003.08230) | 50,394 images; >1.9M instances; 140 categories | Reported 1920×1080; real retail stores/apartments | Group bounding boxes with category and instance count, rather than a box for every heavily occluded item | Unknown; original GitLab redirects to sign-in; [later research implementation](https://github.com/SakiRinn/mmdetection-locount) supplies alternate links |

### Table B: label capabilities (fields 8–11)

| ID | Product annotations | Product tracking IDs | Person IDs | Hand/object interactions |
|---|---|---|---|---|
| 1 | Exact SKU/barcode and boxes | Yes, manually grounded physical instances | Actor/session pseudonyms | Explicit staged event times |
| 2 | ABV barcodes; STAL boxes | Action tubes; persistent cross-action IDs not established | Anonymized; released IDs not established | Basket add/remove |
| 3 | 116 synthetic classes/masks | No dense real-video track ground truth promised | No | Scanning events; no hand/contact graph |
| 4 | 200 classes/boxes/counts | No | No | No |
| 5 | Contact points, no exact SKU boxes | No | Interest-subject pose only; no released global identities | Take/Put/Touch with time and point |
| 6 | 60 classes/masks/boxes | Still-image instance IDs only | No | No |
| 7 | One merchandise class, no exact SKUs | No | No | No |
| 8 | Quadrilaterals, OCR classes/transcripts | No | No | No |
| 9 | 2,000 identities and attributes | No | No | No |
| 10 | 10,000 image-level SKU classes | No | No | No |
| 11 | Inspect-product action, no exact SKUs | No | Subject/session IDs | Reach/retract/hand-in-shelf/inspect actions |
| 12 | 120 product identities/localization | Persistent IDs not established | No | No |
| 13 | 25 coarse grocery categories | No | No | No |
| 14 | 81 fine classes, not hardware SKUs | No | No | No |
| 15 | Product metadata and 3D assets | Asset identity, not physical-instance tracks | No | No |
| 16 | Object categories/masks, not SKUs | VISOR associations, not a retail MOT benchmark | Participant pseudonyms | VISOR hand contact/object relations |
| 17 | Genericized products in QA | No dense MOT ground truth promised | Anonymized | QA interaction classes, not event ledgers |
| 18 | No | No | No | Anomaly labels only |
| 19 | No exact SKUs stated | No | IDs not stated | Normal/stealing classes |
| 20 | Not verified | Not verified | Not verified | Uploader-dependent; not verified |
| 21 | No RGB merchandise | Person IDs, not product tracks | Yes, derived tracker IDs | Pose/anomaly; no product contact |
| 22 | Caption products; no verified SKU boxes | Not stated | Boxes/pose; IDs not stated | Caption-level concealment |
| 23 | No exact SKUs | Person associations; inspect release | Not established | Mall actions, not checkout ledger |
| 24 | Product category plus group count; not necessarily exact SKU | No temporal tracks | No | No |

### Table C: license, publication, usage (fields 12–13 and 15–17)

| ID | Classification, license, publication restrictions | Training suitability | Public GitHub suitability | Pro Express usefulness |
|---|---|---|---|---|
| 1 | Clearly suitable/public with owned recordings and participant publication consent; choose media license | Highest target fit | Selected clips/labels/data card; consent records private | Essential |
| 2 | Research/noncommercial CC BY-NC 4.0; affiliation-email request | Excellent cart events/retrieval | Code and links; samples only under actual license/access terms | Highly relevant, access can delay |
| 3 | Research-only NVIDIA agreement: no general redistribution; models also noncommercial/academic; minimal research-paper excerpts with conditions | Counting/synthetic baseline | Code/evaluation; do not assume recruiter demo qualifies for excerpt exception | Closest one-camera counting benchmark |
| 4 | CC BY-NC-SA 4.0 | Cluttered grocery SKU/count training | Attribution, noncommercial and sharealike requirements | Method benchmark, hardware domain gap |
| 5 | Public Standard.AI custom terms; author/license/NOTICE; no reidentification; additional license above $10k relevant revenue | Multi-view shelf interactions; not dense MOT | Permitted under conditions; [license](https://huggingface.co/datasets/standard-cognition/RetailAction/raw/main/LICENSE) | Best real shelf-interaction release |
| 6 | CC BY-NC-SA 4.0; test labels withheld | Segmentation/copy-paste | Attribution/noncommercial/sharealike | Stacked-object experiment |
| 7 | Exact image redistribution terms not located in original inspected repo | Generic dense boxes, no SKU classifier | Code/downloader; clarify raw-data terms | Less useful than target footage for MVP |
| 8 | Academic only; Det gated | OCR/quad detection | Clarify redistribution before rehosting | Packaging-text extension |
| 9 | Unclear license/access from verified sources | Recognition pretraining after access/terms established | Code/links pending original terms | Large training probably unnecessary |
| 10 | Noncommercial research/education; user responsible for image copyright issues | Fine-grained catalog/customer recognition | Research permission does not establish redistribution permission | Optional pretraining reference |
| 11 | Freely downloadable for research; commercial copying needs permission | Temporal overhead actions | Check release README; use source link/code meanwhile | Small shelf-event benchmark |
| 12 | Unclear original license; web exemplars have separate copyright; old project unavailable here | Small retrieval/domain shift | Code/links until terms established | Feature-matching research |
| 13 | No data license located in inspected original repo | Coarse classification | Code/links; clarify redistribution | Low checkout relevance |
| 14 | Repository MIT; web iconic images/text need separate provenance checks | Fine/coarse classifier | Natural images under repo notices; check third-party assets | Modest baseline |
| 15 | Discrepancy: current S3 says CC BY 4.0; paper/AWS registry says CC BY-NC 4.0; verify actual archive | Rendering/retrieval assets | Actual archive terms and attribution | Synthetic engineering, no events |
| 16 | Project CC BY-NC 4.0; automatic-annotation archive lists different NC government license | Hand/object contacts; domain gap | Attributed examples per component terms | Second-week interaction work |
| 17 | CC BY-NC 4.0 plus no de-anonymization | VLM reasoning; AI labels not transaction truth | Noncommercial attributed subset | Ambitious extension |
| 18 | Questionable publication provenance/consent; no blanket footage redistribution established | Anomaly/CCTV stress tests | Unsuitable for public demo without clearance; code/aggregate metrics | Poor-angle stress-test lead |
| 19 | Lab staged; publisher CC BY 4.0; participant publicity details absent | Small action baseline | Attribution/terms; verify provenance for prominent demo | Staged-action inspiration |
| 20 | Unclear licenses/questionable provenance; uploader license cannot establish source rights | Inspect terms before private experiments | Unsuitable to publish until provenance established | Footage exists, weak checkout truth |
| 21 | PoseLift repo Apache 2.0; RetailS license not located; pose-only release | Human behavior, no SKU detector | PoseLift notices; clarify RetailS terms | Privacy-conscious release example |
| 22 | Publisher CC BY 4.0 free sample; full paid terms separate | Synthetic temporal/pose experiment | Actual sample terms plus attribution | Synthetic lead, missing checkout truth |
| 23 | Publisher CC BY-SA 4.0 | Human action, no SKU training | Attribution/sharealike; inspect participant details | Person behavior baseline |
| 24 | Original data license not established here; original access now gated | Occluded group counting; cannot validate physical instance tracking | Code/source references; clarify data redistribution terms | Relevant alternative to detection counting, but count alone does not establish object identities |

**Potentially legally problematic publication risks:** unauthorized rehosting of CCTV, attempts to reverse anonymization, publishing identifiable covert footage, or acquiring footage from exposed private camera feeds can create privacy, copyright, contractual, or access risks. This is a risk category, not a legal determination about a particular source. The UCF-Crime and Kaggle leads remain in the table for evaluation; a public recruiter demo should use staged recordings unless provenance and publication rights are established. These risks concern proposed uses and do not imply that every release itself is unlawful.

Licensing classifications are source-term summaries, not guarantees of consent or conclusions about a specific publication. A public download and a license label are different evidence. Code licenses, data licenses, pretrained-weight licenses, and permissions to publish identifiable people should be recorded separately. Where unclear, the concrete usable portfolio result is original staged media plus public code; questionable sources remain documented for research evaluation rather than erased from the catalog.

## Important findings and limits

AI City retail references are often misdated. Its 2023 Track 4 is retail; 2024/2025 Track 4 is road objects. The current [access page](https://www.aicitychallenge.org/ai-city-challenge-dataset-access/) lists 2023 Track 4 among datasets still downloadable and says unlisted older datasets are no longer accessible. The ARC generator [repository](https://github.com/yorkeyao/Automated-Retail-Checkout) provides 116 scanned object assets, Unity source, and synthetic class/mask generation under a repository MIT license. That license should not replace the challenge dataset's [NVIDIA data agreement](https://www.aicitychallenge.org/wp-content/uploads/2023/01/Dataset-License-AIC2023-12Jan2023.pdf).

RetailAction's ≤32 selected frames per segment mean irregular sampling: use timestamps, not frame numbers as if they were dense real time. It has no released global shopper identity and cannot validate customer account association. Its paper says labels concern shelves, not baskets or checkout. Take dominates the labels, so evaluate Put and Touch separately.

[PRISM retrieval research](https://arxiv.org/html/2509.14985v1) uses Grocery Vision's ABV cart images with six gallery viewpoints per product. SigLIP → YOLO-E → LightGlue deserves study, but its table reports 42.79% Top-1 and 725 ms/query on A100 despite the abstract's real-time framing. This supports collecting target-domain data instead of assuming a frozen embedding model solves exact SKU recognition. The work is unrelated to DreamVu's PRISM-100K QA dataset.

UCF-Crime and Kaggle surveillance clips are discovery leads, not product-account transaction truth. Public CCTV uploads can have unknown recording permission and ownership chains; face blurring does not grant copyright permissions. Use staged actors for the public Pro Express demo. No private feeds, bypassed logins, or nonpublic retailer systems are needed.

Catalog photos help define names/barcodes, but are not target-camera coverage or automatically licensed for redistribution. Photograph the actual borrowed/purchased products, transcribe barcode/model information, store local project SKU mappings, and use mock prices. Do not claim access to Home Depot's internal product master.

## Self-recorded dataset design

These are engineering estimates, not accuracy guarantees. Record **5–8 products for the MVP**, including a near-lookalike pair and two physical copies of one SKU. Low-cost contractor products could include boxed fasteners, work gloves, tape, sealant cartridges, small fittings, and a borrowed boxed tool. Expand to 10–20 SKUs later, including variants distinguished by model numbers or text.

One camera suffices to prove bounded-lane tracking, SKU inference, and idempotent cart events. Use a fixed elevated oblique view of an entry strip, inspection area, and exit strip. Direct overhead improves separation but may hide packaging faces; oblique views preserve front/side text. Frame tightly enough that the smallest product typically occupies about 80–120 pixels on its short side at 1080p. Measure before recording; this is a practical data-quality target, not a universal detector limit.

Record 1080p at 30 fps with stable light and locked exposure/focus when possible. Optional 4K helps fine-text crops; downsample detector inputs independently. Avoid ultra-wide/fisheye initially. Preserve original videos, timestamps, settings, and manifests. Sixty 15–25 second clips contain 27k–45k raw frames: label diverse sampled frames and retain full videos for tracking/events.

Two phones/webcams improve opposite-view visibility and occlusion recovery but add synchronization, calibration, and duplicate fusion. Add them after the one-camera baseline. A clap or LED visible in both estimates the time offset; measure subsequent clock drift. Opposite/orthogonal views add more useful visibility than cameras side by side.

### MVP recording matrix: 60 clips

| Scenario | Clips | Purpose |
|---|---:|---|
| Isolated views, rotations, handheld approach/departure | 16 | SKU appearance and pose variation |
| One actor with one/two/multiple products | 12 | Detection and basic counting |
| Identical copies and near-lookalikes | 6 | Physical quantity versus SKU identity |
| Occlusion, leave/reenter, reverse movement, putback | 6 | Recovery, reversal, idempotency |
| Empty lane, phone/tool lookalikes, unknown objects | 4 | Hard negatives and unknown rejection |
| Completely held-out transactions | 16 | Exact-cart accuracy and failures |

Record the final 16 test clips separately and never use them for tuning. Split the remaining 44 videos approximately 34 train / 10 validation. Extract 20–40 diverse frames per training video initially (about 700–1,400 images), then mine missed detections and uncertain crops. Aim for 100–200 distinct usable crop views per SKU, not adjacent frames from one turn. Every known SKU needs training and validation captures. Vary actors, background, lighting sessions, and handling for testing. If only one actor is available, disclose that limitation and still hold out sessions. Hold out physical copies or packaging wear when possible.

Extension target: 120–180 transaction clips across 3–5 sessions, 2–3 actors, 10–20 SKUs and two views; 2k–5k diverse training frames plus 200–500 hard-negative/unknown examples. Let held-out failures guide new recording.

### Annotation schema and effort

Label every visible merchandise instance with a box and SKU in sampled training frames. Use visible boxes consistently and include occluded/truncated attributes; do not invent coordinates for fully hidden objects. On 10–20 evaluation clips, annotate persistent physical instance IDs through video using keyframes, interpolation, and corrections at occlusion boundaries. Instances A and B can share one SKU. Ground truth comes from the staged scene, not acceptance of tracker predictions.

Keep event labels separate: video ID, timestamp, physical instance ID, actor/session ID, action (entry, forward/reverse crossing, remove, putback, transfer), and final intended quantity. Write a rulebook first: what counts as inside, when a crossing completes, and whether transfers change ownership. Evaluate event logic independently of detection errors.

Use CVAT video interpolation or SAM2-assisted annotation with human review. Propagation can drift or merge identical objects; it is not ground truth. Estimated effort: 2–4 hours recording/setup and 4–8 hours labeling/review, increasing with overlap and object count. Dense manual annotation of every frame is unnecessary. Share timestamps, camera, and instance conventions across labels.

**Never random-split frames from one video across train/validation/test.** Synchronized views remain in one split and crops inherit their source split. Training-session gallery photos are permitted for known-SKU recognition; test crops must not enter the gallery. Evaluate unknown rejection separately. If claiming new-SKU enrollment without retraining, hold out entire SKUs during training and report that task separately.

### Metrics and difficult tests

Measure detection AP50–95 and small/occluded-item recall; recognition macro Top-1/confusion matrix; unknown false acceptance versus coverage; tracking IDF1/HOTA or ID switches on annotated clips; **exact-cart accuracy**, per-SKU count MAE, duplicate-add rate, missed-item rate, and time to stable cart. Bootstrap by transaction/video rather than correlated frames. Strong frame accuracy can still produce wrong carts.

Test: one item observed in 100+ frames; two identical copies; overlap then separation; short/long occlusion; leave/reentry; hidden replacement by an identical object; reversal; putback; drop/pickup; empty checkout; unknowns; poor views; lighting changes; actor transfers; stacking; departure without confirmation. A fully hidden exchange of identical objects is unobservable to vision alone: return ambiguity/review instead of inventing confidence.

## Dataset combinations that compete

1. **Target videos only:** fastest domain fit and publishable owned media; strongest MVP.
2. **SKU110K/RPC pretraining → target detector → SKU classifier:** may reduce labels; compare against ordinary COCO initialization rather than assume shelf pretraining helps.
3. **Gallery retrieval → target hard-negative metric training:** extensible enrollment; needs all package faces and lookalike rejection.
4. **Own-mask copy-paste + real videos:** inexpensive augmentation; retain real-only testing and limit implausible scale/stacking.
5. **ARC/ABO rendering → camera adaptation:** interesting sim-to-real research; renderer/assets exceed the MVP window.
6. **RetailAction → interaction model → target capture:** good second-week work; irregular sampling and missing SKU truth prevent direct cart validation.
7. **Grocery Vision → cart add/remove engine:** excellent public task match; access and basket occlusion require work.
8. **PRISM-100K → VLM review explanations:** ambitious extension; QA accuracy does not establish item accounting.

Start with option 1 and evaluate options 3/4 as recognition/augmentation ablations. Benchmark target videos before large public-data pretraining.
