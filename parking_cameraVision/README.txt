Parking Project Files
=====================

Included files
--------------
- mask_generator.py
- detector.py

Suggested folder structure
--------------------------
parking_project/
├── inputs/
│   ├── images/
│   └── videos/
├── outputs/
│   ├── masks/
│   └── status/
├── mask_generator.py
└── detector.py

Typical workflow
----------------
1) Put a reference parking lot image in inputs/images/
2) Generate and edit a mask:
   python3 mask_generator.py auto --source inputs/images/lot.jpg --mask lot_mask.png

3) Run editor only later:
   python3 mask_generator.py edit --source inputs/images/lot.jpg --mask lot_mask.png

4) Run the detector on:
   - an image
   - a folder of images
   - a video file
   - webcam index 0
   - a URL / stream OpenCV can open

Examples
--------
python3 mask_generator.py auto --source "inputs/StreetSideImage.png" --mask lot_mask.png
python3 detector.py --source "inputs/StreetSideImage.png" --mask "outputs/masks/lot_mask.png" --show

python3 mask_generator.py edit --source "inputs/test2.mp4" --mask test2_mask.png
python3 detector.py --source "inputs/test2.mp4" --mask "outputs/masks/test2_mask.png" --show


Image:
  python3 detector.py --source inputs/images/lot.jpg --mask outputs/masks/lot_mask.png --show

Folder:
  python3 detector.py --source inputs/images --mask outputs/masks/lot_mask.png --show

Video:
  python3 detector.py --source inputs/videos/parking.mp4 --mask outputs/masks/lot_mask.png --show

Webcam:
  python3 detector.py --source 0 --mask outputs/masks/lot_mask.png --show

URL:
  python3 detector.py --source "http://your-stream-url" --mask outputs/masks/lot_mask.png --show

Notes
-----
- Auto-generated masks are only a first draft. You should review them in the editor.
- The detector currently uses a simple hybrid heuristic. You can later replace that with a trained model.
- Detector defaults are tuned for this project (`on=0.055`, `off=0.035`).
- If a feed shows too many FREE spots, lower thresholds slightly.
- `mask_generator.py` always saves masks in `outputs/masks/`.
- Two files are saved together:
  - `<name>.png`: labeled mask used by `detector.py`
  - `<name>.preview.png`: black/white preview for humans

Command Reference
-----------------
Run from the project root:

1) Create a mask (auto path in outputs/masks/):
   python3 mask_generator.py auto --source inputs/StreetSideImage.png

2) Create a mask (custom name, still saved in outputs/masks/):
   python3 mask_generator.py auto --source inputs/StreetSideImage.png --mask lot_mask.png

3) Auto-generate only (skip editor):
   python3 mask_generator.py auto --source inputs/StreetSideImage.png --no-edit

4) Edit an existing mask:
   python3 mask_generator.py edit --source inputs/StreetSideImage.png --mask lot_mask.png

5) Detect on one image:
   python3 detector.py --source inputs/StreetSideImage.png --mask outputs/masks/lot_mask.png --show

6) Detect on a video:
   python3 detector.py --source inputs/test.mp4 --mask outputs/masks/lot_mask.png --show

7) Detect from webcam:
   python3 detector.py --source 0 --mask outputs/masks/lot_mask.png --show

8) Detect from URL/stream:
   python3 detector.py --source "http://your-stream-url" --mask outputs/masks/lot_mask.png --show

9) Write status JSON to a custom file:
   python3 detector.py --source inputs/StreetSideImage.png --mask outputs/masks/lot_mask.png --out outputs/status/my_status.json
