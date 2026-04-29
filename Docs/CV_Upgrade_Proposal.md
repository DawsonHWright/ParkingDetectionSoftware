# Parking Detection -- Computer Vision Upgrade Proposal

## What We Have Now

The current system works in two steps:

1. **Mask Generation** (`mask_generator.py`)
   - Takes a parking lot image and attempts to auto-detect spots using edge detection and contour finding.
   - The auto-detection is a rough first pass. A human must then open the interactive editor to draw, delete, and adjust spot boundaries manually.
   - Each new camera angle or lot requires repeating this process.

2. **Occupancy Detection** (`detector.py`)
   - Uses the mask to check each spot on every frame.
   - Decides if a spot is occupied using a heuristic based on edge density and frame-to-frame brightness changes.
   - Outputs a JSON status file and can POST updates to a backend.

**Current limitations:**
- Mask generation requires significant manual work per lot/camera.
- The edge-density heuristic is sensitive to lighting changes, shadows, weather, and camera vibration.
- Adding a new lot means someone has to sit down with the editor and draw boxes.

---

## Proposed Upgrades

### Upgrade 1: SAM (Segment Anything Model) for Mask Generation

**What it does:** SAM is a pretrained AI model by Meta that can segment any object in an image. Instead of manually drawing each parking spot, a user would click once inside each spot and SAM auto-draws the precise boundary.

**What changes for the workflow:**
- Open the mask editor with a parking lot image (same as today).
- Click once inside each parking space.
- SAM instantly outlines the full spot boundary -- no dragging, no adjusting.
- Review and save. Done.

**How realistic is this?**
- Very realistic. SAM is a mature, publicly available model with strong Python support.
- The click-to-segment workflow is exactly what SAM was designed for.
- Works best when parking lines are visible. Unmarked gravel lots would be harder.
- The main technical requirement is downloading a model file (375 MB -- 2.5 GB depending on accuracy level).

**Accuracy:**
- High accuracy on lots with painted lines or clear visual boundaries.
- Moderate accuracy on lots without markings (SAM needs some visual contrast to find edges).
- A human still reviews and can fix mistakes before saving. This is a safety net.

**Effort estimate:** 1--2 weeks to integrate into the existing mask editor.

**What's needed:**
- Python packages: `segment-anything` (or SAM 2), `torch`
- Model checkpoint file (one-time download, 375 MB for the lightweight version)
- GPU strongly recommended for comfortable speed. Without a GPU, each click takes ~30--60 seconds. With a GPU, it's under 1 second.
- CPU-only is possible but slower -- acceptable if mask generation is a one-time setup task per lot.

---

### Upgrade 2: YOLO for Occupancy Detection

**What it does:** YOLO (You Only Look Once) is a real-time object detection model. Instead of measuring edge density to guess if a spot is occupied, YOLO directly detects cars and their locations in every frame.

**What changes for the workflow:**
- The detector runs YOLO on each frame to find all cars.
- It checks which mask spots overlap with a detected car.
- Spots with a car in them = occupied. Spots without = free.
- Everything else (JSON output, POST to backend, overlay display) stays the same.

**How realistic is this?**
- Very realistic. YOLO is one of the most widely deployed object detection models in production systems worldwide.
- Pretrained YOLOv8/v11 already knows how to detect cars, trucks, buses, and motorcycles with no custom training needed.
- The `ultralytics` Python package makes integration straightforward.

**Accuracy:**
- Significantly better than the current heuristic in all conditions.
- Handles shadows, lighting changes, rain, and nighttime far better than edge detection.
- Pretrained models achieve ~85--95% accuracy on vehicle detection out of the box.
- Can be fine-tuned on images from our specific lots if even higher accuracy is needed (would require labeling ~100--500 images).

**Effort estimate:** 1--2 weeks to replace the current heuristic in the detector.

**What's needed:**
- Python package: `ultralytics` (installs YOLO and dependencies)
- Model file: YOLOv8n is 6 MB (fast, good accuracy). YOLOv8x is 130 MB (slower, best accuracy).
- GPU is nice to have but not required. YOLOv8n runs at ~30+ FPS on CPU, which is more than enough for parking lot monitoring.
- No custom training data needed for the basic version.

---

### Upgrade 3 (Future): Fully Automatic Mask from Any Image

**What it does:** Combine SAM's segmentation with YOLO's car detection to fully auto-generate a mask with zero human input.

**How it would work:**
1. Point a camera at a lot.
2. YOLO detects all parked cars.
3. SAM segments the spaces between/around them.
4. The system infers a full parking layout automatically.

**How realistic is this?**
- Partially realistic. It works well when the lot is partially full (mix of empty and occupied spots).
- Much harder when the lot is completely full (no visible empty spots to learn from) or completely empty and unmarked.
- Would require meaningful development time and testing across varied lot types.
- This is a longer-term goal, not an immediate deliverable.

**Effort estimate:** 4--8 weeks of R&D with uncertain results.

---

## What About Ground-Level Cameras?

A question was raised about using ground-level photos to generate overhead parking masks.

**The honest answer:**
- Ground-level cameras cause heavy occlusion (cars block other cars). This makes both detection and mask generation unreliable.
- Elevated cameras (rooftop, pole-mounted, 2nd+ floor) are far more practical and produce much better results.
- If only ground-level cameras are available, YOLO-based car detection still works for visible vehicles, but hidden spots behind other cars cannot be monitored from that angle.

**Recommendation:** Use elevated camera positions wherever possible. The detection accuracy difference between elevated and ground-level is significant.

---

## Recommended Roadmap

| Phase | What | Effort | Impact |
|-------|------|--------|--------|
| **Phase 1** | YOLO occupancy detection | 1--2 weeks | Major accuracy improvement, works in all lighting/weather |
| **Phase 2** | SAM-assisted mask editor | 1--2 weeks | 5--10x faster mask setup per lot |
| **Phase 3** | Backend integration (JSON output to Google Cloud) | 1 week | Live status to frontend |
| **Phase 4** | Fully automatic mask generation | 4--8 weeks | Zero-touch setup (R&D, less certain) |

Phases 1--3 are realistic near-term deliverables.
Phase 4 is an R&D effort with a less predictable outcome.

---

## Hardware Requirements Summary

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **Mask generation (SAM)** | CPU (slow, 30--60s per click) | GPU with 4+ GB VRAM (under 1s per click) |
| **Occupancy detection (YOLO)** | CPU (30+ FPS with YOLOv8n) | GPU for larger models or multiple feeds |
| **Camera** | Any IP camera or webcam | Elevated position, 1080p+ |
| **Storage** | ~500 MB for models | ~3 GB if using full-size SAM |

---

## Summary

The two most impactful and realistic upgrades are:

1. **Replace the edge-density heuristic with YOLO car detection.** This directly improves detection accuracy in all conditions with minimal effort and no custom training.

2. **Add SAM click-to-segment to the mask editor.** This makes setting up a new parking lot dramatically faster while keeping human review in the loop for quality.

Both use mature, well-supported open source models and can be integrated into the existing codebase without a rewrite.
