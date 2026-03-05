#!/usr/bin/env python3
"""
Parking Spot Occupancy Detector (OpenCV)

Modes:
  1) label  - click polygon points for each spot, save to spots.json
  2) detect - run occupancy detection on webcam/video/images, output JSON + overlay

Approach:
  - Define each parking spot as a polygon ROI.
  - Compute an "edge density" score inside each ROI (Canny edges).
  - Use hysteresis + temporal smoothing to prevent flicker.
  - Output per-spot occupancy and confidence.

Examples:
  # Label spots from a webcam frame
  python3 parking_detector.py label --source 0 --spots spots.json

  # Label spots from an image
  python3 parking_detector.py label --source test.jpg --spots spots.json

  # Detect from webcam
  python3 parking_detector.py detect --source 0 --spots spots.json --out status.json

  # Detect from a video file
  python3 parking_detector.py detect --source parking.mp4 --spots spots.json --out status.json

  # Detect from an image folder (snapshots)
  python3 parking_detector.py detect --source ./images --spots spots.json --out status.json

  # Post updates to backend
  python3 parking_detector.py detect --source 0 --spots spots.json --post http://localhost:3000/api/spots/update
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

try:
    import requests  # optional (only used if --post is provided)
except Exception:
    requests = None


Point = Tuple[int, int]


@dataclass
class Spot:
    spot_id: str
    polygon: List[Point]


def iso_timestamp_local() -> str:
    # Local-ish timestamp; if you want strict timezone handling, adjust as needed.
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_frame_size(frame: np.ndarray, width: int) -> np.ndarray:
    """Resize frame to a consistent width while preserving aspect ratio."""
    h, w = frame.shape[:2]
    if w == width:
        return frame
    scale = width / float(w)
    new_h = int(round(h * scale))
    return cv2.resize(frame, (width, new_h), interpolation=cv2.INTER_AREA)


def polygon_mask(shape_hw: Tuple[int, int], polygon: List[Point]) -> np.ndarray:
    """Return a uint8 mask (0/255) for the polygon."""
    h, w = shape_hw
    mask = np.zeros((h, w), dtype=np.uint8)
    pts = np.array(polygon, dtype=np.int32).reshape((-1, 1, 2))
    cv2.fillPoly(mask, [pts], 255)
    return mask


def masked_edge_density(gray: np.ndarray, mask: np.ndarray) -> float:
    """Compute edge density inside ROI mask using Canny."""
    # Light blur helps with noise
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # Canny thresholds may need tuning depending on camera
    edges = cv2.Canny(blur, 60, 160)

    roi_edges = cv2.bitwise_and(edges, edges, mask=mask)
    roi_area = float(np.count_nonzero(mask))
    if roi_area <= 0:
        return 0.0

    edge_pixels = float(np.count_nonzero(roi_edges))
    return edge_pixels / roi_area  # 0..1-ish


class OccupancyFilter:
    """
    Stabilize decisions using:
      - hysteresis thresholds
      - temporal majority vote window
    """

    def __init__(
        self,
        on_threshold: float = 0.14,
        off_threshold: float = 0.10,
        history_len: int = 7,
    ):
        self.on_threshold = on_threshold
        self.off_threshold = off_threshold
        self.history_len = history_len
        self._state: Dict[str, bool] = {}
        self._history: Dict[str, List[bool]] = {}

    def update(self, spot_id: str, score: float) -> Tuple[bool, float]:
        """
        Returns:
          occupied (bool), confidence (0..1)
        """
        prev = self._state.get(spot_id, False)

        # Hysteresis decision
        if prev:
            now = score >= self.off_threshold
        else:
            now = score >= self.on_threshold

        # Temporal smoothing (majority vote)
        hist = self._history.setdefault(spot_id, [])
        hist.append(now)
        if len(hist) > self.history_len:
            hist.pop(0)

        occupied = sum(hist) >= (len(hist) // 2 + 1)
        self._state[spot_id] = occupied

        # Confidence: distance from the "decision band" (simple heuristic)
        # You can replace with something better later.
        band_center = (self.on_threshold + self.off_threshold) / 2.0
        spread = max(1e-6, (self.on_threshold - self.off_threshold) / 2.0)
        raw = abs(score - band_center) / spread
        confidence = float(np.clip(raw / 3.0, 0.0, 1.0))  # cap it

        return occupied, confidence


class ParkingDetector:
    def __init__(
        self,
        spots: List[Spot],
        frame_width: int = 960,
        on_threshold: float = 0.14,
        off_threshold: float = 0.10,
        history_len: int = 7,
    ):
        self.spots = spots
        self.frame_width = frame_width
        self.filter = OccupancyFilter(on_threshold, off_threshold, history_len)
        self._masks: Dict[str, np.ndarray] = {}

    def _get_mask(self, frame: np.ndarray, spot: Spot) -> np.ndarray:
        h, w = frame.shape[:2]
        key = f"{spot.spot_id}:{h}x{w}"
        if key not in self._masks:
            self._masks[key] = polygon_mask((h, w), spot.polygon)
        return self._masks[key]

    def analyze(self, frame_bgr: np.ndarray) -> Tuple[List[Dict], np.ndarray]:
        """Return (spot_results, overlay_frame)."""
        frame = ensure_frame_size(frame_bgr, self.frame_width)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        results: List[Dict] = []
        overlay = frame.copy()

        for spot in self.spots:
            mask = self._get_mask(frame, spot)
            score = masked_edge_density(gray, mask)
            occupied, confidence = self.filter.update(spot.spot_id, score)

            results.append(
                {
                    "id": spot.spot_id,
                    "occupied": bool(occupied),
                    "confidence": round(float(confidence), 3),
                    "score": round(float(score), 5),
                }
            )

            # Draw overlay
            pts = np.array(spot.polygon, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(overlay, [pts], isClosed=True, color=(255, 255, 255), thickness=2)

            fill = overlay.copy()
            color = (0, 0, 255) if occupied else (0, 255, 0)  # red/green
            cv2.fillPoly(fill, [pts], color)
            overlay = cv2.addWeighted(fill, 0.25, overlay, 0.75, 0)

            # Label
            # Put label at polygon centroid
            cx = int(np.mean([p[0] for p in spot.polygon]))
            cy = int(np.mean([p[1] for p in spot.polygon]))
            txt = f"{spot.spot_id}:{'OCC' if occupied else 'FREE'}"
            cv2.putText(
                overlay,
                txt,
                (cx - 20, cy),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        return results, overlay


def load_spots(path: str) -> List[Spot]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    spots = []
    for s in data.get("spots", []):
        poly = [(int(x), int(y)) for x, y in s["polygon"]]
        spots.append(Spot(spot_id=str(s["id"]), polygon=poly))
    return spots


def save_spots(path: str, spots: List[Spot], camera_id: str = "lot-1") -> None:
    data = {
        "cameraId": camera_id,
        "spots": [{"id": s.spot_id, "polygon": s.polygon} for s in spots],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def is_image_file(p: str) -> bool:
    ext = os.path.splitext(p)[1].lower()
    return ext in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def list_images(folder: str) -> List[str]:
    items = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if os.path.isfile(p) and is_image_file(p):
            items.append(p)
    return items


# --------------------------
# Labeling tool (mouse UI)
# --------------------------

class SpotLabeler:
    def __init__(self, frame: np.ndarray):
        self.frame = frame.copy()
        self.display = frame.copy()
        self.current_points: List[Point] = []
        self.spots: List[Spot] = []
        self.next_id_num = 1

    def _redraw(self):
        self.display = self.frame.copy()

        # Draw existing spots
        for s in self.spots:
            pts = np.array(s.polygon, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(self.display, [pts], True, (255, 255, 255), 2)
            cx = int(np.mean([p[0] for p in s.polygon]))
            cy = int(np.mean([p[1] for p in s.polygon]))
            cv2.putText(self.display, s.spot_id, (cx, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Draw current polygon being created
        for p in self.current_points:
            cv2.circle(self.display, p, 4, (0, 255, 255), -1)

        if len(self.current_points) >= 2:
            pts = np.array(self.current_points, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(self.display, [pts], False, (0, 255, 255), 2)

        help_text = "Click points. Keys: [n]=new spot, [u]=undo point, [d]=delete last spot, [s]=save, [q]=quit"
        cv2.putText(self.display, help_text, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

    def on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.current_points.append((int(x), int(y)))
            self._redraw()

    def run(self, out_spots_path: str, camera_id: str = "lot-1"):
        cv2.namedWindow("label", cv2.WINDOW_NORMAL)
        cv2.setMouseCallback("label", self.on_mouse)
        self._redraw()

        while True:
            cv2.imshow("label", self.display)
            key = cv2.waitKey(20) & 0xFF

            if key == ord("q"):
                break

            if key == ord("u"):  # undo point
                if self.current_points:
                    self.current_points.pop()
                    self._redraw()

            if key == ord("n"):  # finalize current spot
                if len(self.current_points) < 3:
                    print("Need at least 3 points for a polygon.")
                else:
                    spot_id = f"S{self.next_id_num}"
                    self.next_id_num += 1
                    self.spots.append(Spot(spot_id=spot_id, polygon=self.current_points.copy()))
                    self.current_points.clear()
                    self._redraw()

            if key == ord("d"):  # delete last spot
                if self.spots:
                    self.spots.pop()
                    self._redraw()

            if key == ord("s"):  # save
                save_spots(out_spots_path, self.spots, camera_id=camera_id)
                print(f"Saved {len(self.spots)} spots to {out_spots_path}")

        cv2.destroyAllWindows()
        # Auto-save on exit if something exists
        if self.spots:
            save_spots(out_spots_path, self.spots, camera_id=camera_id)
            print(f"Saved {len(self.spots)} spots to {out_spots_path} (on exit)")


# --------------------------
# Sources
# --------------------------

def open_source(source: str) -> Tuple[str, Union[int, str]]:
    """
    Returns a tuple (kind, value)
      kind: 'cam' | 'video' | 'image' | 'folder'
    """
    if source.isdigit():
        return ("cam", int(source))
    if os.path.isdir(source):
        return ("folder", source)
    if os.path.isfile(source) and is_image_file(source):
        return ("image", source)
    return ("video", source)  # assume a video path / stream url


def post_payload(url: str, payload: dict, timeout_s: float = 2.0) -> None:
    if requests is None:
        raise RuntimeError("requests is not installed. pip install requests")
    try:
        r = requests.post(url, json=payload, timeout=timeout_s)
        r.raise_for_status()
    except Exception as e:
        print(f"[WARN] POST failed: {e}")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_label = sub.add_parser("label", help="Label parking spots (polygons) and save to spots.json")
    p_label.add_argument("--source", required=True, help="0 for webcam, image path, or video path")
    p_label.add_argument("--spots", required=True, help="Output spots.json path")
    p_label.add_argument("--width", type=int, default=960, help="Standardized frame width")
    p_label.add_argument("--camera-id", default="lot-1", help="Camera/Lot identifier")

    p_detect = sub.add_parser("detect", help="Run detection using spots.json")
    p_detect.add_argument("--source", required=True, help="0 for webcam, video path, image path, or folder of images")
    p_detect.add_argument("--spots", required=True, help="Input spots.json path")
    p_detect.add_argument("--width", type=int, default=960, help="Standardized frame width")
    p_detect.add_argument("--out", default="status.json", help="Output status JSON path")
    p_detect.add_argument("--every", type=float, default=1.0, help="Seconds between status updates")
    p_detect.add_argument("--show", action="store_true", help="Show overlay window")
    p_detect.add_argument("--post", default="", help="POST URL for backend updates (optional)")
    p_detect.add_argument("--on", type=float, default=0.14, help="Threshold to switch FREE->OCC")
    p_detect.add_argument("--off", type=float, default=0.10, help="Threshold to switch OCC->FREE")
    p_detect.add_argument("--history", type=int, default=7, help="Temporal smoothing history length")

    args = parser.parse_args()

    kind, val = open_source(args.source)

    if args.cmd == "label":
        # Grab one frame (from camera/video) or load image
        if kind == "image":
            frame = cv2.imread(val)
            if frame is None:
                raise RuntimeError(f"Could not read image: {val}")
        else:
            cap = cv2.VideoCapture(val)
            if not cap.isOpened():
                raise RuntimeError(f"Could not open source: {args.source}")
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                raise RuntimeError("Could not read a frame from source.")

        frame = ensure_frame_size(frame, args.width)
        SpotLabeler(frame).run(args.spots, camera_id=args.camera_id)
        return

    # detect mode
    spots = load_spots(args.spots)
    if not spots:
        raise RuntimeError("No spots found in spots.json. Run label mode first.")

    detector = ParkingDetector(
        spots=spots,
        frame_width=args.width,
        on_threshold=args.on,
        off_threshold=args.off,
        history_len=args.history,
    )

    # Load cameraId from file to include in payload
    with open(args.spots, "r", encoding="utf-8") as f:
        spots_data = json.load(f)
    camera_id = spots_data.get("cameraId", "lot-1")

    last_emit = 0.0

    def emit(results: List[Dict]) -> None:
        payload = {
            "cameraId": camera_id,
            "timestamp": iso_timestamp_local(),
            "spots": [{"id": r["id"], "occupied": r["occupied"], "confidence": r["confidence"]} for r in results],
        }
        # write to file
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(json.dumps(payload))

        # optionally POST
        if args.post:
            post_payload(args.post, payload)

    if kind in ("cam", "video"):
        cap = cv2.VideoCapture(val)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open source: {args.source}")

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            now = time.time()
            results, overlay = detector.analyze(frame)

            if args.show:
                cv2.imshow("parking", overlay)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

            if now - last_emit >= args.every:
                emit(results)
                last_emit = now

        cap.release()
        cv2.destroyAllWindows()

    elif kind == "image":
        frame = cv2.imread(val)
        if frame is None:
            raise RuntimeError(f"Could not read image: {val}")
        results, overlay = detector.analyze(frame)
        emit(results)
        if args.show:
            cv2.imshow("parking", overlay)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

    elif kind == "folder":
        images = list_images(val)
        if not images:
            raise RuntimeError(f"No images found in folder: {val}")

        for path in images:
            frame = cv2.imread(path)
            if frame is None:
                continue
            results, overlay = detector.analyze(frame)
            emit(results)
            if args.show:
                cv2.imshow("parking", overlay)
                key = cv2.waitKey(300) & 0xFF
                if key == ord("q"):
                    break
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()