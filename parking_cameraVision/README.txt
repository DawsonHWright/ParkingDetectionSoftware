Parking Project Files
=====================

Included files
--------------
- mask_generator.py   -- Generate and edit parking masks (with optional SAM support)
- detector.py         -- Detect occupied/free spots (YOLO or legacy heuristic)
- requirements.txt    -- Python dependencies

Suggested folder structure
--------------------------
parking_project/
├── inputs/
│   ├── images/
│   └── videos/
├── outputs/
│   ├── masks/
│   └── status/
├── models/
│   └── sam_vit_b_01ec64.pth    (SAM checkpoint, auto-downloaded or manual)
├── mask_generator.py
├── detector.py
└── requirements.txt

Setup
-----
1) Install dependencies:
   pip install -r requirements.txt

2) For GPU support (recommended), install PyTorch with CUDA:
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

3) The SAM model checkpoint should be in models/sam_vit_b_01ec64.pth
   Download from: https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth

4) YOLO model weights are downloaded automatically on first run.

Typical workflow
----------------
1) Put a reference parking lot image in inputs/images/

2) Generate and edit a mask:
   python3 mask_generator.py auto --source inputs/images/lot.jpg --mask lot_mask.png

3) Generate a mask with SAM-assisted editing (click to auto-segment spots):
   python3 mask_generator.py auto --source inputs/images/lot.jpg --mask lot_mask.png --sam

4) Edit an existing mask:
   python3 mask_generator.py edit --source inputs/images/lot.jpg --mask lot_mask.png
   python3 mask_generator.py edit --source inputs/images/lot.jpg --mask lot_mask.png --sam

5) Run the detector on:
   - an image
   - a folder of images
   - a video file
   - webcam index 0
   - a URL / stream OpenCV can open

Detection Examples
------------------
YOLO detection (default, recommended):
  python3 detector.py --source inputs/images/lot.jpg --mask outputs/masks/lot_mask.png --show

Legacy heuristic detection:
  python3 detector.py --source inputs/images/lot.jpg --mask outputs/masks/lot_mask.png --detector heuristic --show

Video:
  python3 detector.py --source inputs/videos/parking.mp4 --mask outputs/masks/lot_mask.png --show

Webcam:
  python3 detector.py --source 0 --mask outputs/masks/lot_mask.png --show

URL/stream:
  python3 detector.py --source "http://your-stream-url" --mask outputs/masks/lot_mask.png --show

POST to backend:
  python3 detector.py --source 0 --mask outputs/masks/lot_mask.png --post "https://your-backend.com/api/update"

Write status JSON:
  python3 detector.py --source inputs/images/lot.jpg --mask outputs/masks/lot_mask.png --out outputs/status/my_status.json

Mask Editor Controls
--------------------
  D  -- Draw mode (drag to add a rectangular spot)
  R  -- Remove mode (click to delete a spot)
  A  -- SAM mode (click inside a spot to auto-segment it; requires --sam)
  V  -- View mode (no editing)
  S  -- Save mask
  X  -- Reset mask to original
  H  -- Toggle help overlay
  Q  -- Quit editor

Detector CLI Options
--------------------
  --detector yolo|heuristic   Detection backend (default: yolo)
  --yolo-model MODEL          YOLO model size: yolov8n, yolov8s, yolov8m, yolov8l, yolov8x
  --yolo-conf FLOAT           YOLO confidence threshold (default: 0.25)
  --iou-thresh FLOAT          Min spot/vehicle overlap to count as occupied (default: 0.15)
  --camera-id ID              Identifier in JSON output (default: lot-1)
  --out PATH                  JSON output path (default: outputs/status/status.json)
  --post URL                  POST JSON updates to this URL
  --every SECONDS             Seconds between updates (default: 1.0)
  --history N                 Temporal smoothing frames (default: 5)
  --show                      Show overlay window

JSON Output Format
------------------
{
  "cameraId": "lot-1",
  "timestamp": "2026-04-09T14:30:00-05:00",
  "spots": [
    { "id": "S1", "occupied": true },
    { "id": "S2", "occupied": false }
  ]
}

Notes
-----
- YOLO detection is significantly more accurate than the legacy heuristic,
  especially in varying lighting, shadows, and weather.
- SAM click-to-segment makes mask setup much faster than manual drawing.
- The SAM model (375 MB) only needs to be downloaded once.
- YOLO model weights (~6 MB for yolov8n) are cached after first download.
- GPU (CUDA) is recommended for SAM. YOLO runs well on CPU.
