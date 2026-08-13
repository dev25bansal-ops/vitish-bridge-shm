"""
cv/inference.py — crack detection inference API (YOLO-seg preferred, OpenCV
Canny/contour heuristic fallback so detections ALWAYS render at demo time).

CrackDetector is the single entry point the backend calls:
    det = CrackDetector()
    dets = det.detect(image_bgr)   # list[dict]
    # each dict: {'cls':'crack','conf':0.87,'box':[x,y,w,h],
    #             'mask': np.uint8 binary, 'mask_rle': str,'area_px':int,'severity':0-1}

Behaviour:
  * If models/weights/crack_seg.pt exists, an ultralytics YOLO-seg model is
    loaded and used preferentially (guard against missing ultralytics).
  * Otherwise (or on load failure) a pure-OpenCV Canny/contour heuristic
    segments "crack-like" elongated dark regions — ZERO weights required.
  * severity = area-weighted crack burden, clamped to 0..1.

detect_webcam(index=0) runs a live FPS loop for the demo camera feed.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import cv2

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEIGHTS = REPO_ROOT / "models" / "weights" / "crack_seg.pt"


def mask_to_rle(binary_mask: np.ndarray) -> str:
    """Encode a binary mask as a COCO-style run-length string (column-major).

    Uses the same algorithm as pycocotools.mask.encode without the dependency.
    """
    mask = (np.asarray(binary_mask) > 0).astype(np.uint8)
    h, w = mask.shape
    flat = mask.flatten(order="F").astype(np.uint8)
    flat = np.concatenate([[0], flat, [0]])
    runs = np.where(flat[1:] != flat[:-1])[0] + 1
    runs[1::2] -= runs[0::2]
    return json.dumps({"counts": [int(r) for r in runs], "size": [int(h), int(w)]})


class CrackDetector:
    """YOLO-seg crack detector with an always-available OpenCV fallback."""

    def __init__(self, weights_path: str | Path = DEFAULT_WEIGHTS, conf: float = 0.25,
                 iou: float = 0.45, device: str | None = None) -> None:
        self.weights_path = Path(weights_path)
        self.conf = float(conf)
        self.iou = float(iou)
        self._model = None
        self.mode = "heuristic (no YOLO weights / ultralytics)"

        if self.weights_path.exists():
            try:
                from ultralytics import YOLO
                self._model = YOLO(str(self.weights_path))
                self.mode = f"yolo-seg ({self.weights_path.name}, conf={self.conf})"
            except Exception as exc:
                print(f"  [cv] WARNING: could not load YOLO model ({exc}); "
                      "using Canny/contour heuristic fallback.")
                self._model = None
        else:
            print(f"  [cv] no weights at {self.weights_path} -> Canny/contour heuristic mode. "
                  "Train with: python models/cv/train_yolo.py")

    # ---------------------------------------------------------------- detect
    def detect(self, image_bgr: np.ndarray) -> list[dict]:
        """Detect cracks in a BGR image. Always returns a list of dicts."""
        if image_bgr is None or image_bgr.size == 0:
            return []
        if self._model is not None:
            try:
                dets = self._detect_yolo(image_bgr)
                if dets:
                    return dets
            except Exception as exc:
                print(f"  [cv] WARNING: yolo inference failed ({exc}); heuristic fallback.")
        return self._detect_heuristic(image_bgr)

    # ------------------------------------------------------------ yolo path
    def _detect_yolo(self, image_bgr: np.ndarray) -> list[dict]:
        h, w = image_bgr.shape[:2]
        results = self._model.predict(source=image_bgr, conf=self.conf, iou=self.iou,
                                      verbose=False)
        dets: list[dict] = []
        for r in results:
            if r.masks is None or r.boxes is None:
                continue
            masks = r.masks.data.cpu().numpy()
            boxes = r.boxes.xyxy.cpu().numpy()
            confs = r.boxes.conf.cpu().numpy()
            for i in range(len(boxes)):
                mask_bin = (masks[i] > 0.5).astype(np.uint8) * 255
                area_px = int(np.count_nonzero(mask_bin))
                x1, y1, x2, y2 = boxes[i]
                box = [float(x1), float(y1), float(x2 - x1), float(y2 - y1)]
                dets.append(self._pack("crack", float(confs[i]), box, mask_bin, area_px, h, w))
        return dets

    # -------------------------------------------------------- heuristic path
    def _detect_heuristic(self, image_bgr: np.ndarray) -> list[dict]:
        h, w = image_bgr.shape[:2]
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 40, 110)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        diag = float(np.hypot(h, w))
        dets: list[dict] = []
        for c in contours:
            length = cv2.arcLength(c, closed=False)
            area = float(cv2.contourArea(c))
            if length < 0.10 * diag or area < 30:
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            elongation = (cv2.arcLength(c, True) ** 2) / max(4 * np.pi * area, 1.0)
            # cracks are long + thin -> high elongation and long relative length
            conf = 0.30 + 0.45 * min(1.0, length / (0.35 * diag)) + 0.15 * min(1.0, (elongation - 1) / 3.0)
            conf = float(min(0.95, max(0.05, conf)))
            mask_bin = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(mask_bin, [c], -1, 255, -1)
            area_px = int(area)
            dets.append(self._pack("crack", conf, [float(x), float(y), float(bw), float(bh)],
                                   mask_bin, area_px, h, w))
        dets.sort(key=lambda d: d["area_px"], reverse=True)
        return dets

    @staticmethod
    def _pack(cls: str, conf: float, box: list[float], mask_bin: np.ndarray,
              area_px: int, h: int, w: int) -> dict:
        severity = float(min(1.0, area_px / max(1, int(0.05 * h * w))))
        return {
            "cls": cls,
            "conf": float(conf),
            "box": [round(box[0], 1), round(box[1], 1), round(box[2], 1), round(box[3], 1)],
            "mask": mask_bin,
            "mask_rle": mask_to_rle(mask_bin),
            "area_px": area_px,
            "severity": round(severity, 4),
        }

    # -------------------------------------------------------------- webcam
    def detect_webcam(self, index: int = 0, show: bool = True) -> None:
        """Live detection loop with FPS display. Press 'q' to quit."""
        cap = cv2.VideoCapture(int(index))
        if not cap.isOpened():
            print(f"ERROR: could not open camera index {index}. "
                  "Try another index or the dataset/demo frames instead.")
            return
        print(f"  [cv] webcam {index} live (mode: {self.mode}). Press 'q' to quit.")
        t_prev = time.time()
        fps = 0.0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                t0 = time.time()
                dets = self.detect(frame)
                dt = max(time.time() - t0, 1e-6)
                fps = 0.9 * fps + 0.1 * (1.0 / dt)
                for d in dets:
                    x, y, bw, bh = [int(v) for v in d["box"]]
                    cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 0, 255), 2)
                    label = f"{d['cls']} {d['conf']:.2f} sev={d['severity']:.2f}"
                    cv2.putText(frame, label, (x, max(15, y - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                cv2.putText(frame, f"FPS {fps:.1f} | {len(dets)} det | {self.mode}",
                            (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
                if show:
                    cv2.imshow("CrackDetector", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                else:
                    print(f"  [cv] {len(dets)} dets, fps={fps:.1f}")
                    time.sleep(0.1)
        finally:
            cap.release()
            cv2.destroyAllWindows()
        print("  [cv] webcam loop ended.")


def demo_frame(size: int = 320, seed: int = 0) -> np.ndarray:
    """Return a synthetic concrete image with a crack (for offline demos)."""
    try:
        from .prep_sdnet import make_crack_image
    except ImportError:
        from prep_sdnet import make_crack_image
    img, _ = make_crack_image(size, seed=int(seed))
    return img


if __name__ == "__main__":  # self-test (heuristic path, offline)
    syspath = str(Path(__file__).resolve().parent)
    import sys
    if syspath not in sys.path:
        sys.path.insert(0, syspath)
    from prep_sdnet import make_crack_image
    det = CrackDetector(weights_path=Path("no_such_weights.pt"))
    img, _ = make_crack_image(256, seed=5)
    dets = det.detect(img)
    assert any(d["cls"] == "crack" for d in dets), "heuristic should find the synthetic crack"
    d0 = dets[0]
    assert "box" in d0 and "mask" in d0 and "mask_rle" in d0 and "severity" in d0
    print(f"cv/inference.py self-test PASS mode={det.mode} "
          f"n_det={len(dets)} conf={d0['conf']:.2f} area={d0['area_px']}px sev={d0['severity']:.3f}")
