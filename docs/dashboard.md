# 🖥️ Inspecting the checkout lane

The dashboard has four tabs and a scenario title screen. **Live lane** shows the rendered camera evidence, physical objects, events and cart. **Decisions** explains ledger membership and review blocks. **Models** and **Benchmark** load measured results from the local reports.

## 📷 Camera evidence

The Live lane camera selector switches between the configured **lane** and **overhead** views. The image, resolution and bounding boxes all come from the same processed frame group:

- The selected image is `snapshot.frames[camera_id]`.
- Boxes are filtered to detections with the matching `camera` value.
- The JPEG URL includes the camera, run and frame identifiers.
- A missing view shows a notice. An older camera image is never carried forward into a newer group.
- A legacy single-camera snapshot still works through `snapshot.frame`; unlabeled legacy boxes belong to the lane camera.

The **Overlays** switch hides the predicted boxes. In image mode the camera also shows image-space checkout zones. In calibrated mode those pixel-row zones are suppressed: the shared physical boundaries appear on the map instead.

## 🗺️ Calibrated coverage

The map uses `snapshot.geometry`, with `/api/reports.geometry` as a loading fallback. Its extent, lane width, approach and commit lines, camera locations and footprints come from the exported calibration. Both axes use the same meter scale. Travel runs left to right, in the **+z** direction; each grid square is one meter.

| Visual | Meaning |
|---|---|
| Blue footprint | Lane camera's geometric coverage |
| Purple footprint | Overhead camera's geometric coverage |
| Green overlap | Both calibrated footprints cover this region |
| Diagonal hatch | Neither calibrated footprint covers this region |
| Filled product dot | Product observed in the latest processed group |
| Hollow, faded product dot | Last observed position of a product that is currently hidden |
| Product trail | Recent observed positions of that canonical physical object |
| Check inside a dot | The physical object currently belongs to the cart |
| Pink dashed ring | This object has unresolved review evidence |

Clicking a footprint legend button also switches the video view. Colors for the same canonical object remain consistent between its boxes, dot and trail. A new scenario run clears the trails.

**Coverage is geometric, not a visibility guarantee.** The footprints describe the calibrated carry-height plane (currently 0.9 m). People, carts and products can still block a camera. Hidden dots show a recorded position, not a predicted current location. Camera symbols outside the displayed map extent are pinned to its edge; their tooltip contains the actual 3D position.

Without calibration, the map explains that the engine is using single-view image-space tracking. Missing cameras and unresolved SKU or identity evidence remain visible, and checkout confirmation stays blocked whenever the ledger requests review.

The **Parked flatbed** scenario card uses an ordinary resize of frame 70 from development seed 0. It is rendered RGB evidence from the synthetic benchmark, rather than an illustration.
