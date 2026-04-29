#!/usr/bin/env python3
"""
detector.py

Use a saved parking mask to detect which spots are occupied or free.
Supports image, folder, video, webcam index, and URL/stream inputs.

Detection backends:
  yolo      -- YOLOv8 vehicle detection (default, recommended)
  heuristic -- Legacy edge-density + frame-diff method
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

try:
    import requests
except Exception:
    requests = None

Box = Tuple[int, int, int, int]

VEHICLE_CLASSES = {2, 3, 5, 7}  # COCO: car, motorcycle, bus, truck (used with --vehicle-only)


def ensure_parent_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def is_image_file(path: str) -> bool:
    return Path(path).suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def resize_keep_aspect(image: np.ndarray, width: int) -> np.ndarray:
    h, w = image.shape[:2]
    if width <= 0 or w == width:
        return image
    scale = width / float(w)
    new_h = int(round(h * scale))
    return cv2.resize(image, (width, new_h), interpolation=cv2.INTER_AREA)


def open_source(source: str) -> Tuple[str, Union[int, str]]:
    if os.path.isdir(source):
        return ("folder", source)
    if os.path.isfile(source) and is_image_file(source):
        return ("image", source)
    if source.isdigit():
        return ("stream", int(source))
    return ("stream", source)


def read_image_folder(folder: str) -> List[str]:
    return sorted([str(p) for p in Path(folder).iterdir() if p.is_file() and is_image_file(str(p))])


def load_mask(mask_path: str, target_shape: Optional[Tuple[int, int]] = None) -> np.ndarray:
    mask = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)
    if mask is None:
        raise RuntimeError(f"Could not read mask: {mask_path}")
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    if target_shape is not None and mask.shape[:2] != target_shape:
        target_h, target_w = target_shape
        mask = cv2.resize(mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
    return mask


def mask_to_spots(mask: np.ndarray) -> List[Box]:
    unique_vals = [int(v) for v in np.unique(mask) if int(v) != 0]
    boxes: List[Box] = []

    if len(unique_vals) <= 1:
        binary = ((mask > 127).astype(np.uint8) * 255)
        total_labels, _, stats, _ = cv2.connectedComponentsWithStats(binary, 8, cv2.CV_32S)
        for i in range(1, total_labels):
            x = int(stats[i, cv2.CC_STAT_LEFT])
            y = int(stats[i, cv2.CC_STAT_TOP])
            w = int(stats[i, cv2.CC_STAT_WIDTH])
            h = int(stats[i, cv2.CC_STAT_HEIGHT])
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area < 25:
                continue
            boxes.append((x, y, w, h))
        return boxes

    for label_val in sorted(unique_vals):
        ys, xs = np.where(mask == label_val)
        area = int(xs.size)
        if area < 25:
            continue
        x_min = int(xs.min())
        y_min = int(ys.min())
        x_max = int(xs.max()) + 1
        y_max = int(ys.max()) + 1
        boxes.append((x_min, y_min, x_max - x_min, y_max - y_min))

    boxes.sort(key=lambda b: (b[1], b[0]))
    return boxes


# ---------------------------------------------------------------------------
# YOLO detection backend
# ---------------------------------------------------------------------------

def load_yolo_model(model_size: str = "yolov8n"):
    from ultralytics import YOLO
    model = YOLO(f"{model_size}.pt")
    return model


def detect_vehicles(model, frame: np.ndarray, conf: float = 0.25, vehicle_only: bool = False) -> List[Box]:
    """Run YOLO and return bounding boxes for detected objects.

    When vehicle_only=False (default), any detection counts -- this handles
    overhead/angled cameras where cars get misclassified by shape.
    Detections larger than 25% of frame area are discarded (false positives like
    "train" spanning the whole image).
    """
    results = model(frame, conf=conf, verbose=False)
    frame_h, frame_w = frame.shape[:2]
    max_det_area = frame_w * frame_h * 0.25
    boxes: List[Box] = []
    for det in results:
        for box_data in det.boxes:
            cls_id = int(box_data.cls[0])
            if vehicle_only and cls_id not in VEHICLE_CLASSES:
                continue
            x1, y1, x2, y2 = box_data.xyxy[0].cpu().numpy()
            w = int(x2 - x1)
            h = int(y2 - y1)
            if w * h > max_det_area:
                continue
            boxes.append((int(x1), int(y1), w, h))
    return boxes


def box_iou(a: Box, b: Box) -> float:
    """Intersection-over-minimum-area between two (x, y, w, h) boxes.

    Uses the minimum area of the two boxes as the denominator so that a small
    parking spot fully covered by a large vehicle detection scores ~1.0.
    """
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix1 = max(ax, bx)
    iy1 = max(ay, by)
    ix2 = min(ax + aw, bx + bw)
    iy2 = min(ay + ah, by + bh)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    min_area = min(aw * ah, bw * bh)
    return inter / max(float(min_area), 1e-6)


def yolo_spot_occupancy(spots: List[Box], vehicles: List[Box], iou_thresh: float = 0.15) -> List[bool]:
    """For each spot, return True if any vehicle overlaps above the threshold."""
    occupied = []
    for spot in spots:
        hit = any(box_iou(spot, v) >= iou_thresh for v in vehicles)
        occupied.append(hit)
    return occupied


# ---------------------------------------------------------------------------
# Legacy heuristic detection backend
# ---------------------------------------------------------------------------

def calc_edge_density(gray_roi: np.ndarray) -> float:
    blur = cv2.GaussianBlur(gray_roi, (5, 5), 0)
    edges = cv2.Canny(blur, 60, 160)
    return float(np.count_nonzero(edges)) / float(edges.size + 1e-6)


def calc_mean_diff(roi1: np.ndarray, roi2: Optional[np.ndarray]) -> float:
    if roi2 is None:
        return 0.0
    return float(abs(np.mean(roi1.astype(np.float32)) - np.mean(roi2.astype(np.float32))))


# ---------------------------------------------------------------------------
# Temporal smoothing (shared by both backends)
# ---------------------------------------------------------------------------

class SpotStateManager:
    def __init__(self, history_len: int, on_threshold: float = 0.5, off_threshold: float = 0.5):
        self.history_len = history_len
        self.on_threshold = on_threshold
        self.off_threshold = off_threshold
        self.state: Dict[int, bool] = {}
        self.history: Dict[int, deque] = {}

    def update(self, spot_idx: int, occupied_raw: bool) -> bool:
        hist = self.history.setdefault(spot_idx, deque(maxlen=self.history_len))
        hist.append(occupied_raw)
        occupied = sum(hist) >= (len(hist) // 2 + 1)
        self.state[spot_idx] = occupied
        return occupied

    def update_score(self, spot_idx: int, score: float) -> bool:
        """Legacy interface for the heuristic backend."""
        prev = self.state.get(spot_idx, False)
        current = score >= (self.off_threshold if prev else self.on_threshold)
        return self.update(spot_idx, current)


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------

def emit_payload(camera_id: str, results: List[Dict], output_path: str, post_url: str = "") -> None:
    payload = {
        "cameraId": camera_id,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "spots": results,
    }
    ensure_parent_dir(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(json.dumps(payload))

    if post_url:
        if requests is None:
            print("[WARN] requests is not installed, so POST was skipped.")
            return
        try:
            resp = requests.post(post_url, json=payload, timeout=3)
            resp.raise_for_status()
        except Exception as exc:
            print(f"[WARN] POST failed: {exc}")


# ---------------------------------------------------------------------------
# Frame analysis
# ---------------------------------------------------------------------------

def analyze_frame_yolo(
    frame: np.ndarray,
    spots: List[Box],
    manager: SpotStateManager,
    yolo_model,
    yolo_conf: float,
    iou_thresh: float,
    vehicle_only: bool = False,
) -> Tuple[List[Dict], np.ndarray]:
    overlay = frame.copy()
    vehicles = detect_vehicles(yolo_model, frame, conf=yolo_conf, vehicle_only=vehicle_only)
    raw_occ = yolo_spot_occupancy(spots, vehicles, iou_thresh=iou_thresh)

    results = []
    free_count = 0
    for idx, ((x, y, w, h), raw) in enumerate(zip(spots, raw_occ), start=1):
        occupied = manager.update(idx, raw)
        if not occupied:
            free_count += 1
        color = (0, 0, 255) if occupied else (0, 255, 0)
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 2)
        cv2.putText(overlay, f"S{idx}:{'OCC' if occupied else 'FREE'}", (x, max(18, y - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2)
        results.append({"id": f"S{idx}", "occupied": bool(occupied)})

    for vx, vy, vw, vh in vehicles:
        cv2.rectangle(overlay, (vx, vy), (vx + vw, vy + vh), (255, 180, 0), 1)

    cv2.rectangle(overlay, (20, 20), (430, 80), (0, 0, 0), -1)
    cv2.putText(overlay, f"Available spots: {free_count} / {len(spots)}", (35, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    return results, overlay


def analyze_frame_heuristic(
    frame: np.ndarray,
    previous_frame: Optional[np.ndarray],
    spots: List[Box],
    manager: SpotStateManager,
) -> Tuple[List[Dict], np.ndarray]:
    overlay = frame.copy()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    prev_gray = None if previous_frame is None else cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)

    results = []
    free_count = 0
    for idx, (x, y, w, h) in enumerate(spots, start=1):
        roi = gray[y:y+h, x:x+w]
        prev_roi = None if prev_gray is None else prev_gray[y:y+h, x:x+w]
        edge_density = calc_edge_density(roi)
        mean_diff = calc_mean_diff(roi, prev_roi)
        score = (0.75 * edge_density) + (0.25 * min(mean_diff / 64.0, 1.0))
        occupied = manager.update_score(idx, score)
        if not occupied:
            free_count += 1
        color = (0, 0, 255) if occupied else (0, 255, 0)
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 2)
        cv2.putText(overlay, f"S{idx}:{'OCC' if occupied else 'FREE'}", (x, max(18, y - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2)
        results.append({"id": f"S{idx}", "occupied": bool(occupied)})

    cv2.rectangle(overlay, (20, 20), (430, 80), (0, 0, 0), -1)
    cv2.putText(overlay, f"Available spots: {free_count} / {len(spots)}", (35, 58),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    return results, overlay


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Parking detector using a saved mask.")
    parser.add_argument("--source", required=True, help="Image, folder, webcam index, video file, or URL")
    parser.add_argument("--mask", required=True, help="Mask image path")
    parser.add_argument("--detector", choices=["yolo", "heuristic"], default="yolo",
                        help="Detection backend (default: yolo)")
    parser.add_argument("--yolo-model", default="yolov8n", help="YOLO model size (default: yolov8n)")
    parser.add_argument("--yolo-conf", type=float, default=0.25, help="YOLO confidence threshold")
    parser.add_argument("--iou-thresh", type=float, default=0.15,
                        help="Min overlap to count a vehicle as occupying a spot")
    parser.add_argument("--vehicle-only", action="store_true",
                        help="Only count YOLO vehicle classes (car/truck/bus/motorcycle). "
                             "Default: any detection counts, which handles overhead cameras better.")
    parser.add_argument("--width", type=int, default=1280, help="Resize frames to this width")
    parser.add_argument("--camera-id", default="lot-1", help="Identifier included in JSON output")
    parser.add_argument("--out", default="outputs/status/status.json", help="JSON output path")
    parser.add_argument("--post", default="", help="Optional backend URL to POST updates to")
    parser.add_argument("--every", type=float, default=1.0, help="Seconds between emitted updates")
    parser.add_argument("--history", type=int, default=5, help="Temporal smoothing history length")
    parser.add_argument("--on-threshold", type=float, default=0.055,
                        help="(heuristic only) Threshold FREE -> OCC")
    parser.add_argument("--off-threshold", type=float, default=0.035,
                        help="(heuristic only) Threshold OCC -> FREE")
    parser.add_argument("--show", action="store_true", help="Show overlay window")
    args = parser.parse_args()

    use_yolo = args.detector == "yolo"
    yolo_model = None
    if use_yolo:
        print(f"Loading YOLO model: {args.yolo_model} ...")
        yolo_model = load_yolo_model(args.yolo_model)
        print("YOLO model loaded.")

    if use_yolo:
        manager = SpotStateManager(args.history)
    else:
        manager = SpotStateManager(args.history, args.on_threshold, args.off_threshold)

    kind, src = open_source(args.source)
    previous_frame = None
    last_emit_time = 0.0

    def process_frame(frame: np.ndarray, mask_resized: np.ndarray, spots: List[Box]) -> bool:
        nonlocal previous_frame, last_emit_time
        frame = resize_keep_aspect(frame, args.width)
        if frame.shape[:2] != mask_resized.shape[:2]:
            mask_resized = cv2.resize(mask_resized, (frame.shape[1], frame.shape[0]),
                                      interpolation=cv2.INTER_NEAREST)
            spots = mask_to_spots(mask_resized)

        if use_yolo:
            results, overlay = analyze_frame_yolo(
                frame, spots, manager, yolo_model, args.yolo_conf, args.iou_thresh,
                vehicle_only=args.vehicle_only)
        else:
            results, overlay = analyze_frame_heuristic(frame, previous_frame, spots, manager)

        now = time.time()
        if now - last_emit_time >= args.every:
            emit_payload(args.camera_id, results, args.out, args.post)
            last_emit_time = now

        if args.show:
            cv2.imshow("parking_detector", overlay)
            key = cv2.waitKey(1 if kind == "stream" else 200) & 0xFF
            if key == ord("q"):
                return False

        previous_frame = frame.copy()
        return True

    if kind == "image":
        frame = cv2.imread(src)
        if frame is None:
            raise RuntimeError(f"Could not read image: {src}")
        frame = resize_keep_aspect(frame, args.width)
        mask = load_mask(args.mask, frame.shape[:2])
        spots = mask_to_spots(mask)
        print(f"Loaded {len(spots)} spots from mask: {args.mask}")
        process_frame(frame, mask, spots)
        if args.show:
            cv2.waitKey(0)
            cv2.destroyAllWindows()

    elif kind == "folder":
        images = read_image_folder(src)
        if not images:
            raise RuntimeError(f"No images found in folder: {src}")
        first_frame = cv2.imread(images[0])
        if first_frame is None:
            raise RuntimeError(f"Could not read first image: {images[0]}")
        first_frame = resize_keep_aspect(first_frame, args.width)
        mask = load_mask(args.mask, first_frame.shape[:2])
        spots = mask_to_spots(mask)
        print(f"Loaded {len(spots)} spots from mask: {args.mask}")
        for image_path in images:
            frame = cv2.imread(image_path)
            if frame is None:
                continue
            if not process_frame(frame, mask, spots):
                break
        cv2.destroyAllWindows()

    else:
        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            if isinstance(src, str) and os.path.isfile(src):
                raise RuntimeError(
                    f"Could not open video file: {src}. The file may be corrupt or encoded in an unsupported way."
                )
            raise RuntimeError(f"Could not open source: {src}")
        ok, first_frame = cap.read()
        if not ok or first_frame is None:
            cap.release()
            raise RuntimeError(f"Could not read first frame from source: {src}")
        first_frame = resize_keep_aspect(first_frame, args.width)
        mask = load_mask(args.mask, first_frame.shape[:2])
        spots = mask_to_spots(mask)
        print(f"Loaded {len(spots)} spots from mask: {args.mask}")
        if not process_frame(first_frame, mask, spots):
            cap.release()
            cv2.destroyAllWindows()
            return
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            if not process_frame(frame, mask, spots):
                break
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
