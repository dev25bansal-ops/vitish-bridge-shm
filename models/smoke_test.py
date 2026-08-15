"""
models/smoke_test.py — verify the ALWAYS-WORKING demo fallbacks.

Runs WITHOUT any data download and WITHOUT trained weights:
  [1] vibration heuristic scoring            (features.py + heuristic.py)
  [2] vibration AnomalyDetector inference    (infer.py, fallback path)
  [3] MiniRocket + Ridge fallback           (minirocket_fallback.py)
  [4] CV crack heuristic on a synthetic image (cv/inference.py + prep_sdnet)
  [5] BHI fusion trajectory 87 -> RED       (fusion/bhi.py via contract)

Run from the repo root:
    python models/smoke_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

PASS = 0


def ok(cond: bool, line: str) -> None:
    global PASS
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {line}")
    if not cond:
        raise SystemExit(f"SMOKE TEST FAILED: {line}")
    PASS += 1


def synth_window(amp: float, extra: float = 0.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(1024) / 100.0
    base = (0.05 * np.sin(2 * np.pi * 2.0 * t) + 0.04 * np.sin(2 * np.pi * 5.5 * t)
            + 0.02 * np.sin(2 * np.pi * 9.0 * t) + 0.01 * rng.standard_normal(1024))
    return base * amp + extra * rng.standard_normal(1024)


def test_heuristic() -> None:
    from models.vibration.heuristic import HeuristicAnomalyScorer
    sc = HeuristicAnomalyScorer(fs=100.0)
    s0, u0 = sc.score(synth_window(1.0, seed=1))
    ok(s0 == 0.0 and u0 == 1.0, "heuristic: no baseline -> (0,1) honest warm-up")
    for i in range(12):
        sc.update_healthy(synth_window(1.0, seed=10 + i))
    s_h, u_h = sc.score(synth_window(1.0, seed=100))
    s_d, u_d = sc.score(synth_window(1.8, extra=0.03, seed=200))
    ok(s_h < 0.35, f"heuristic: healthy scores low ({s_h:.3f} < 0.35)")
    ok(s_d > s_h and s_d > 0.5, f"heuristic: damaged scores high ({s_d:.3f} > {s_h:.3f})")
    ok(0.0 <= u_h <= 1.0 and 0.0 <= u_d <= 1.0, "heuristic: uncertainty in [0,1]")


def test_infer() -> None:
    from models.vibration.infer import AnomalyDetector, REPO_ROOT
    det = AnomalyDetector(n_healthy=8, weights_dir=REPO_ROOT / "models" / "weights" / "smoke_empty")
    for i in range(8):
        s, u = det.score(synth_window(1.0, seed=100 + i))
        assert s == 0.0 and u == 1.0
    s_h, u_h = det.score(synth_window(1.0, seed=900))
    s_d, u_d = det.score(synth_window(1.9, extra=0.03, seed=901))
    ok(s_d > s_h, f"AnomalyDetector fallback: damaged({s_d:.3f}) > healthy({s_h:.3f})")
    ok(det.rms_flag(synth_window(2.0, seed=7)) is True, "AnomalyDetector: edge rms_flag fires")
    ok(det.mode.startswith("heuristic"), f"AnomalyDetector: mode='{det.mode}'")


def test_minirocket() -> None:
    from models.vibration.minirocket_fallback import make_fallback_scorer
    healthy = np.stack([synth_window(1.0, seed=50 + i) for i in range(20)])
    damaged = np.stack([synth_window(1.7 + 0.1 * i, extra=0.03, seed=300 + i) for i in range(20)])
    sc = make_fallback_scorer(healthy, damaged, n_kernels=200)
    s_h, u_h = sc.score(synth_window(1.0, seed=99))
    s_d, u_d = sc.score(synth_window(2.1, extra=0.05, seed=99))
    ok(s_d > s_h, f"MiniRocket+Ridge: damaged({s_d:.3f}) > healthy({s_h:.3f})")
    ok(0.0 <= u_d <= 1.0, "MiniRocket+Ridge: uncertainty in [0,1]")


def test_cv() -> None:
    from models.cv.prep_sdnet import make_crack_image
    from models.cv.inference import CrackDetector
    img, mask = make_crack_image(256, seed=5)
    assert int(np.count_nonzero(mask)) > 30, "synthetic crack mask should be non-trivial"
    det = CrackDetector(weights_path=Path(__file__).resolve().parent / "weights" / "smoke_no_weights.pt")
    dets = det.detect(img)
    ok(len(dets) >= 1, f"crack heuristic: found {len(dets)} detection(s) on synthetic crack image")
    if dets:
        d = dets[0]
        keys = {"cls", "conf", "box", "mask", "mask_rle", "area_px", "severity"}
        ok(keys <= d.keys(), f"crack heuristic: detection dict keys {sorted(keys & d.keys())}")
        ok(d["cls"] == "crack" and d["severity"] >= 0.0 and d["severity"] <= 1.0,
           f"crack heuristic: cls/severity valid (sev={d['severity']})")
        ok("counts" in d["mask_rle"], "crack heuristic: mask_rle is COCO-style")
    # a clean (no-crack) image should not produce confident detections
    clean = np.full((256, 256, 3), 150, np.uint8)
    dets_clean = det.detect(clean)
    ok(all(x["conf"] < 0.95 for x in dets_clean), "crack heuristic: clean image stays low-confidence")
    # strict (return_yolo_only) mode with no model loaded returns [] — the
    # heuristic is never consulted, so clean-frame verification measures the
    # real model and the demo clean-frame policy can't flicker (ROADMAP line 39)
    strict = det.detect(img, return_yolo_only=True)
    ok(strict == [], "crack heuristic: strict mode with no YOLO model returns [] (heuristic never consulted)")


def test_bhi() -> None:
    from models.fusion.bhi import BridgeHealthIndex, demo
    bhi = BridgeHealthIndex()
    msg0 = bhi.update(0.22, 0.12, 0.00, uncertainty=0.15)
    ok(msg0["bhi"] == 87.0, f"BHI: baseline 87.0 (got {msg0['bhi']})")
    ok(msg0["state"] == "GREEN", f"BHI: state GREEN (got {msg0['state']})")
    msg = bhi.update(0.90, 0.85, 0.40, uncertainty=0.45)
    ok(msg["state"] == "RED", f"BHI: critical -> RED (got {msg['state']})")
    ok(msg["bhi"] < msg0["bhi"], f"BHI: monotone drop {msg0['bhi']} -> {msg['bhi']}")
    ok(0.0 <= msg["u"] <= 20.0, f"BHI: uncertainty in +/- BHI points ({msg['u']})")
    demo()  # prints the auditable trajectory


def main() -> None:
    print("=" * 70)
    print("models/smoke_test.py — always-working fallback verification (no downloads)")
    print("=" * 70)
    test_heuristic()
    test_infer()
    test_minirocket()
    test_cv()
    test_bhi()
    print("=" * 70)
    print(f"ALL SMOKE TESTS PASSED ({PASS} PASS lines, 0 FAIL)")


if __name__ == "__main__":
    main()
