#!/usr/bin/env python3
"""
mask_generator.py

Generate and edit a parking-spot mask from a reference image, video, camera index,
or stream URL.

Modes:
  auto  -- Auto-generate a mask via edge detection, then open the editor.
  edit  -- Edit an existing mask interactively.

The editor supports manual drawing, removal, and SAM-assisted click-to-segment.

Examples
--------
python3 mask_generator.py auto --source inputs/images/lot.jpg --mask lot_mask.png
python3 mask_generator.py edit --source inputs/images/lot.jpg --mask lot_mask.png
python3 mask_generator.py auto --source inputs/images/lot.jpg --sam
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import os
import platform
import re
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

Point = Tuple[int, int]
MASK_OUTPUT_DIR = Path("outputs") / "masks"
DEFAULT_SAM_CHECKPOINT = Path(__file__).resolve().parent / "models" / "sam_vit_b_01ec64.pth"
SAM_MODEL_TYPE = "vit_b"


# ---------------------------------------------------------------------------
# SAM helpers
# ---------------------------------------------------------------------------

def load_sam_predictor(checkpoint: str, model_type: str = SAM_MODEL_TYPE):
    """Load SAM model and return a SamPredictor ready for set_image()."""
    import torch
    from segment_anything import sam_model_registry, SamPredictor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading SAM model ({model_type}) on {device} ...")
    sam = sam_model_registry[model_type](checkpoint=checkpoint)
    sam.to(device)
    predictor = SamPredictor(sam)
    print("SAM model loaded.")
    return predictor


def sam_segment_at_point(predictor, x: int, y: int) -> Optional[np.ndarray]:
    """Given a SamPredictor with an image already set, segment at (x, y).

    Returns a binary mask (uint8, 0/255) or None if segmentation failed.
    """
    point_coords = np.array([[x, y]])
    point_labels = np.array([1])  # 1 = foreground
    masks, scores, _ = predictor.predict(
        point_coords=point_coords,
        point_labels=point_labels,
        multimask_output=True,
    )
    if masks is None or len(masks) == 0:
        return None
    best_idx = int(np.argmax(scores))
    return (masks[best_idx].astype(np.uint8) * 255)


# ---------------------------------------------------------------------------
# Display / filesystem helpers
# ---------------------------------------------------------------------------

def display_available() -> bool:
    if platform.system().lower() != "linux":
        return True
    display = os.environ.get("DISPLAY")
    if not display:
        return False

    x11_lib_path = ctypes.util.find_library("X11")
    if not x11_lib_path:
        return False

    try:
        x11 = ctypes.CDLL(x11_lib_path)
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        conn = x11.XOpenDisplay(display.encode("utf-8"))
        if not conn:
            return False
        x11.XCloseDisplay(conn)
        return True
    except Exception:
        return False


def ensure_parent_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def sanitize_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return cleaned or "parking"


def default_mask_path(source: str) -> str:
    source_path = Path(source)
    if source_path.exists() and source_path.name:
        base = sanitize_name(source_path.stem)
    elif source.isdigit():
        base = f"camera_{source}"
    else:
        base = sanitize_name(source)
    return str(MASK_OUTPUT_DIR / f"{base}_mask.png")


def resolve_mask_path(source: str, requested_mask_path: str) -> str:
    if requested_mask_path:
        name = Path(requested_mask_path).name
    else:
        name = Path(default_mask_path(source)).name
    if Path(name).suffix.lower() != ".png":
        name = f"{Path(name).stem}.png"
    return str(MASK_OUTPUT_DIR / name)


def preview_mask_path(mask_path: str) -> str:
    p = Path(mask_path)
    return str(p.with_name(f"{p.stem}.preview.png"))


def save_mask_with_preview(mask: np.ndarray, mask_path: str) -> None:
    ensure_parent_dir(mask_path)
    save_mask = mask if int(mask.max()) > 255 else mask.astype(np.uint8)
    cv2.imwrite(mask_path, save_mask)
    preview = ((mask > 0).astype(np.uint8) * 255)
    preview_path = preview_mask_path(mask_path)
    cv2.imwrite(preview_path, preview)
    print(f"Saved mask: {mask_path}")
    print(f"Saved preview: {preview_path}")


def is_image_file(path: str) -> bool:
    return Path(path).suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def resize_keep_aspect(image: np.ndarray, width: int) -> np.ndarray:
    h, w = image.shape[:2]
    if width <= 0 or w == width:
        return image
    scale = width / float(w)
    new_h = int(round(h * scale))
    return cv2.resize(image, (width, new_h), interpolation=cv2.INTER_AREA)


def read_frame_from_source(source: str, width: int) -> np.ndarray:
    if os.path.isdir(source):
        files = sorted([str(p) for p in Path(source).iterdir() if p.is_file() and is_image_file(str(p))])
        if not files:
            raise FileNotFoundError(f"No images found in folder: {source}")
        image = cv2.imread(files[0])
        if image is None:
            raise RuntimeError(f"Could not read image: {files[0]}")
        return resize_keep_aspect(image, width)

    if os.path.isfile(source) and is_image_file(source):
        image = cv2.imread(source)
        if image is None:
            raise RuntimeError(f"Could not read image: {source}")
        return resize_keep_aspect(image, width)

    cap_source = int(source) if source.isdigit() else source
    cap = cv2.VideoCapture(cap_source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open source: {source}")

    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError(f"Could not read a frame from source: {source}")

    return resize_keep_aspect(frame, width)


# ---------------------------------------------------------------------------
# Legacy auto-generation (edge-based)
# ---------------------------------------------------------------------------

def preprocess_for_lines(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    edges = cv2.Canny(blur, 60, 160)
    combined = cv2.bitwise_or(thresh, edges)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)
    return combined


def non_max_suppression_boxes(boxes: List[Tuple[int, int, int, int]], overlap_thresh: float) -> List[Tuple[int, int, int, int]]:
    if not boxes:
        return []

    rects = np.array([[x, y, x + w, y + h] for (x, y, w, h) in boxes], dtype=np.float32)
    x1 = rects[:, 0]
    y1 = rects[:, 1]
    x2 = rects[:, 2]
    y2 = rects[:, 3]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    idxs = np.argsort(y2)
    picked = []

    while len(idxs) > 0:
        last = idxs[-1]
        picked.append(last)
        suppress = [len(idxs) - 1]
        for pos in range(len(idxs) - 1):
            i = idxs[pos]
            xx1 = max(x1[last], x1[i])
            yy1 = max(y1[last], y1[i])
            xx2 = min(x2[last], x2[i])
            yy2 = min(y2[last], y2[i])
            w = max(0.0, xx2 - xx1 + 1)
            h = max(0.0, yy2 - yy1 + 1)
            overlap = (w * h) / areas[i]
            if overlap > overlap_thresh:
                suppress.append(pos)
        idxs = np.delete(idxs, suppress)

    out = []
    for i in picked:
        xx1, yy1, xx2, yy2 = rects[i].astype(int)
        out.append((xx1, yy1, xx2 - xx1, yy2 - yy1))
    return out


def auto_generate_mask(image: np.ndarray, min_area: int, max_area_ratio: float) -> np.ndarray:
    prep = preprocess_for_lines(image)
    h, w = prep.shape[:2]
    image_area = float(h * w)
    max_area = image_area * max_area_ratio
    contours, _ = cv2.findContours(prep, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates: List[Tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area = bw * bh
        if area < min_area or area > max_area:
            continue
        aspect = bw / float(max(1, bh))
        if not (0.25 <= aspect <= 4.0):
            continue
        if bw < 12 or bh < 12:
            continue
        candidates.append((x, y, bw, bh))

    merged = non_max_suppression_boxes(candidates, overlap_thresh=0.25)
    mask = np.zeros((h, w), dtype=np.uint8)
    for (x, y, bw, bh) in merged:
        cv2.rectangle(mask, (x, y), (x + bw, y + bh), 255, -1)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    return mask


def mask_to_label_map(mask: np.ndarray) -> np.ndarray:
    binary = (mask > 0).astype(np.uint8)
    total_labels, labels, _, _ = cv2.connectedComponentsWithStats(binary, 8, cv2.CV_32S)
    label_map = np.zeros_like(labels, dtype=np.uint16)
    for i in range(1, total_labels):
        label_map[labels == i] = i
    return label_map


# ---------------------------------------------------------------------------
# Interactive mask editor
# ---------------------------------------------------------------------------

class MaskEditor:
    """Interactive editor with manual draw/remove and SAM click-to-segment."""

    def __init__(self, image: np.ndarray, mask: np.ndarray, sam_predictor=None):
        self.image = image
        self.original_mask = mask_to_label_map(mask)
        self.mask = self.original_mask.copy()
        self.display_help = True
        self.mode = "view"  # view, draw, remove, sam
        self.sam_predictor = sam_predictor
        self.sam_ready = sam_predictor is not None
        self.drag_start: Optional[Point] = None
        self.drag_current: Optional[Point] = None
        self.window_name = "mask_editor"

        if self.sam_ready:
            print("Encoding image for SAM (one-time step) ...")
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            self.sam_predictor.set_image(rgb)
            print("SAM image encoded. Press A to enter SAM mode.")

    def _connected_components_boxes(self) -> List[Tuple[int, int, int, int]]:
        boxes = []
        label_ids = [int(v) for v in np.unique(self.mask) if int(v) != 0]
        for label_id in label_ids:
            ys, xs = np.where(self.mask == label_id)
            if xs.size == 0:
                continue
            x_min = int(xs.min())
            y_min = int(ys.min())
            x_max = int(xs.max()) + 1
            y_max = int(ys.max()) + 1
            boxes.append((x_min, y_min, x_max - x_min, y_max - y_min))
        return boxes

    def _delete_box_at(self, point: Point) -> None:
        x, y = point
        if x < 0 or y < 0 or y >= self.mask.shape[0] or x >= self.mask.shape[1]:
            return
        label_id = int(self.mask[y, x])
        if label_id <= 0:
            return
        self.mask[self.mask == label_id] = 0

    def _next_label(self) -> int:
        current_max = int(self.mask.max())
        if current_max >= 65535:
            raise RuntimeError("Too many spots in mask (label limit reached).")
        return current_max + 1

    def _add_sam_segment(self, x: int, y: int) -> None:
        if not self.sam_ready:
            print("SAM not loaded. Start with --sam to enable.")
            return
        seg_mask = sam_segment_at_point(self.sam_predictor, x, y)
        if seg_mask is None:
            print(f"SAM: no segment found at ({x}, {y})")
            return
        if seg_mask.shape[:2] != self.mask.shape[:2]:
            seg_mask = cv2.resize(seg_mask, (self.mask.shape[1], self.mask.shape[0]),
                                  interpolation=cv2.INTER_NEAREST)
        area = int(np.count_nonzero(seg_mask))
        if area < 25:
            print(f"SAM: segment too small ({area} px)")
            return
        label = self._next_label()
        self.mask[seg_mask > 127] = label
        print(f"SAM: added spot (label={label}, area={area} px)")

    def _draw_overlay(self) -> np.ndarray:
        canvas = self.image.copy()
        mask_color = np.zeros_like(canvas)
        mask_color[:, :, 1] = ((self.mask > 0).astype(np.uint8) * 255)
        canvas = cv2.addWeighted(canvas, 0.85, mask_color, 0.35, 0)

        boxes = self._connected_components_boxes()
        for i, (x, y, w, h) in enumerate(boxes, start=1):
            cv2.rectangle(canvas, (x, y), (x + w, y + h), (255, 255, 255), 2)
            cv2.putText(canvas, f"S{i}", (x, max(18, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

        if self.drag_start and self.drag_current:
            x1, y1 = self.drag_start
            x2, y2 = self.drag_current
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 255), 2)

        mode_label = self.mode.upper()
        if self.mode == "sam":
            mode_label = "SAM (click to segment)"
        cv2.rectangle(canvas, (10, 10), (340, 40), (0, 0, 0), -1)
        cv2.putText(canvas, f"Mode: {mode_label}", (16, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        if self.display_help:
            lines = [
                "D: draw mode (left drag to add)",
                "R: remove mode (left click to delete)",
                "A: SAM mode (click to auto-segment spot)",
                "V: view mode",
                "S: save   X: reset   H: help   Q: quit",
            ]
            if not self.sam_ready:
                lines[2] = "A: SAM mode (not loaded, use --sam)"
            y = 24
            for line in lines:
                cv2.putText(canvas, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                y += 24
        return canvas

    def _mouse_callback(self, event, x, y, flags, userdata):
        if self.mode == "draw":
            if event == cv2.EVENT_LBUTTONDOWN:
                self.drag_start = (x, y)
                self.drag_current = (x, y)
            elif event == cv2.EVENT_MOUSEMOVE and self.drag_start is not None:
                self.drag_current = (x, y)
            elif event == cv2.EVENT_LBUTTONUP and self.drag_start is not None:
                x1, y1 = self.drag_start
                x2, y2 = x, y
                x_min, x_max = sorted((x1, x2))
                y_min, y_max = sorted((y1, y2))
                if (x_max - x_min) >= 8 and (y_max - y_min) >= 8:
                    label = self._next_label()
                    cv2.rectangle(self.mask, (x_min, y_min), (x_max, y_max), int(label), -1)
                self.drag_start = None
                self.drag_current = None
        elif self.mode == "remove":
            if event == cv2.EVENT_LBUTTONDOWN:
                self._delete_box_at((x, y))
        elif self.mode == "sam":
            if event == cv2.EVENT_LBUTTONDOWN:
                self._add_sam_segment(x, y)

    def run(self, save_path: str) -> None:
        if not display_available():
            raise RuntimeError(
                "Mask editor requires a working graphical display, but this runtime cannot open one. "
                "Use `auto --no-edit` to generate/save a mask without opening the editor."
            )
        ensure_parent_dir(save_path)
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)

        def save_now() -> None:
            save_mask_with_preview(self.mask, save_path)

        while True:
            overlay = self._draw_overlay()
            cv2.imshow(self.window_name, overlay)
            key = cv2.waitKey(20) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("s"):
                save_now()
            elif key == ord("r"):
                self.mode = "remove"
                self.drag_start = None
                self.drag_current = None
                print("Switched to remove mode.")
            elif key == ord("d"):
                self.mode = "draw"
                print("Switched to draw mode.")
            elif key == ord("a"):
                if self.sam_ready:
                    self.mode = "sam"
                    self.drag_start = None
                    self.drag_current = None
                    print("Switched to SAM mode. Click inside a parking spot to auto-segment it.")
                else:
                    print("SAM not loaded. Restart with --sam to enable SAM mode.")
            elif key == ord("v"):
                self.mode = "view"
                self.drag_start = None
                self.drag_current = None
                print("Switched to view mode.")
            elif key == ord("x"):
                self.mask = self.original_mask.copy()
                print("Mask reset to original state.")
            elif key == ord("h"):
                self.display_help = not self.display_help
        cv2.destroyWindow(self.window_name)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-generate and/or edit a parking lot mask.")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    auto_parser = subparsers.add_parser("auto", help="Auto-generate a mask, then open the editor.")
    auto_parser.add_argument("--source", required=True, help="Image/video/folder/webcam index/stream URL")
    auto_parser.add_argument("--mask", default="", help="Output mask name/path (saved under outputs/masks/)")
    auto_parser.add_argument("--width", type=int, default=1280, help="Resize reference frame to this width")
    auto_parser.add_argument("--min-area", type=int, default=250, help="Minimum candidate rectangle area")
    auto_parser.add_argument("--max-area-ratio", type=float, default=0.05,
                             help="Maximum rectangle area as a fraction of image area")
    auto_parser.add_argument("--no-edit", action="store_true",
                             help="Do not open the interactive editor after auto-generating the mask")
    auto_parser.add_argument("--sam", action="store_true", help="Enable SAM click-to-segment in the editor")
    auto_parser.add_argument("--sam-checkpoint", default=str(DEFAULT_SAM_CHECKPOINT),
                             help="Path to SAM model checkpoint")

    edit_parser = subparsers.add_parser("edit", help="Edit an existing mask only.")
    edit_parser.add_argument("--source", required=True,
                             help="Reference image/video/folder/webcam index/stream URL")
    edit_parser.add_argument("--mask", default="",
                             help="Existing mask name/path (looked up under outputs/masks/)")
    edit_parser.add_argument("--width", type=int, default=1280, help="Resize reference frame to this width")
    edit_parser.add_argument("--sam", action="store_true", help="Enable SAM click-to-segment in the editor")
    edit_parser.add_argument("--sam-checkpoint", default=str(DEFAULT_SAM_CHECKPOINT),
                             help="Path to SAM model checkpoint")

    args = parser.parse_args()
    image = read_frame_from_source(args.source, args.width)
    mask_path = resolve_mask_path(args.source, args.mask)

    sam_predictor = None
    if args.sam:
        sam_predictor = load_sam_predictor(args.sam_checkpoint)

    if args.mode == "auto":
        mask = auto_generate_mask(image, min_area=args.min_area, max_area_ratio=args.max_area_ratio)
        mask = mask_to_label_map(mask)
        save_mask_with_preview(mask, mask_path)
        print(f"Initial auto-generated mask saved to: {mask_path}")
        if args.no_edit:
            return
        MaskEditor(image, mask, sam_predictor=sam_predictor).run(mask_path)
    else:
        if not os.path.exists(mask_path):
            raise FileNotFoundError(f"Mask file not found: {mask_path}")
        mask = cv2.imread(mask_path, cv2.IMREAD_UNCHANGED)
        if mask is None:
            raise RuntimeError(f"Could not read mask: {mask_path}")
        if mask.ndim == 3:
            mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
        if mask.shape[:2] != image.shape[:2]:
            mask = cv2.resize(mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)
        MaskEditor(image, mask, sam_predictor=sam_predictor).run(mask_path)


if __name__ == "__main__":
    main()
