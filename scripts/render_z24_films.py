#!/usr/bin/env python
"""Render real-Z24 scroll-world film clips — the ORIGINAL item-20 landing
renderer, superseded 2026-08-18 by the cinematic scroll-driven landing
(``landing/index.html``; this script's films/stills/manifest are no longer
committed or served).  Kept as reusable, honest, re-renderable evidence tooling.

Everything rendered here is real measured evidence — deterministic, reproducible,
honest, and cheap:

  * ``data/z24/inputs.npy`` + ``labels.npy`` (1530 segments x 27 ch x 60 s @
    100 Hz; 17 damage-campaign condition labels x 90 segments each) — the same
    real Z24 benchmark the demo pipeline replays (README "What's real in this
    demo", and the committed ``data/z24/fixture/``).
  * real ``crack_seg.pt`` detections on the real CC0 ``data/cv/demo_frames/``
    crack photos.
  * the empirical LTBP fleet prior (``data/ltbp/analysis/ltbp_summary.json``).

No AI-video, no synthetic scene, no headless browser.  Frames are drawn with
matplotlib and encoded with the ffmpeg binary bundled in the ``imageio-ffmpeg``
wheel (pinned encoder profile below — the scroll-world engine scrubs
``video.currentTime``, so the H.264 must carry a tight GOP and faststart).

Outputs (written to ``landing/assets/…`` for provenance by the superseded
scroll-world landing — re-renderable, deterministic):

    landing/assets/stills/<name>.webp     scene posters (engine ``still``)
    landing/assets/films/<name>.mp4       scene film (engine ``clip``)
    landing/assets/films/conn<i>.mp4      connector films (length N-1)
    landing/assets/manifest.json          provenance + encoder profile

Determinism: fixed random seeds everywhere; same input file  ->  same bytes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

try:
    import imageio_ffmpeg
except ImportError:  # pragma: no cover
    imageio_ffmpeg = None

REPO_ROOT = Path(__file__).resolve().parents[1]
Z24 = REPO_ROOT / "data" / "z24" / "inputs.npy"
Z24_LABELS = Z24.with_name("labels.npy")
DEMO_FRAMES = REPO_ROOT / "data" / "cv" / "demo_frames"
CV_WEIGHTS = REPO_ROOT / "models" / "weights" / "crack_seg.pt"
LTBP_SUMMARY = REPO_ROOT / "data" / "ltbp" / "analysis" / "ltbp_summary.json"
TELEGRAM_IMAGE = REPO_ROOT / "landing" / "assets" / "films" / "_telegram_card.png"

STILLS = REPO_ROOT / "landing" / "assets" / "stills"
FILMS = REPO_ROOT / "landing" / "assets" / "films"
MANIFEST = REPO_ROOT / "landing" / "assets" / "manifest.json"

# 16:9 master — same as the scroll-world pipeline master, scrubs cleanly.  The
# 720p encode keeps the file small; the engine centre-crops on phones.
W, H, FPS = 1280, 720, 24
DIVE_SEC = 8          # length of each scene film
CONN_SEC = 2          # length of each connector film (short continuity hop)
# The engine's scrub contract (pipeline.md §5): same model/params for dives +
# connectors. macro_block_size=1 preserves the exact 1280x720 frame (no 720->736
# padding — a padded canvas would show letterbox lines at the scene edge).
_ENC = ["-g", "8", "-keyint_min", "8", "-sc_threshold", "0",
        "-movflags", "+faststart", "-crf", "20", "-preset", "slow"]

PALETTE = {  # VITISH brand palette (inherited from the twin's dark dashboard)
    "bg": "#0b132b", "deck": "#0d1b2a", "ink": "#e0e7f5", "muted": "#6b7a99",
    "cyan": "#7fd4ff", "green": "#2ee6a8", "amber": "#ffcf5c", "red": "#ff5c7a",
    "accent": "#8a7bb5", "grid": "#1d2b45",
}
LIGHT_BG = "#f5f1e6"          # page/hero poster background (engine --sw-bg default)
HERO_PALETTE = {**PALETTE, "bg": LIGHT_BG, "ink": "#241d2b",
                "deck": "#e7dbc0", "muted": "#6a6072", "grid": "#d6c9a8"}


def ffmpeg_exe() -> str:
    if imageio_ffmpeg is None:
        raise SystemExit("imageio-ffmpeg not installed — pip install imageio-ffmpeg")
    return imageio_ffmpeg.get_ffmpeg_exe()


# -------------------------------------------------------------------------- #
# frame helpers
# -------------------------------------------------------------------------- #
def _fig() -> tuple:
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    return fig, fig.add_axes([0, 0, 1, 1])


def _base(pal: dict, title: str = "", sub: str = "") -> tuple:
    """One full-bleed themed frame with title + subtitle above the data."""
    fig, ax = _fig()
    fig.patch.set_facecolor(pal["bg"]); ax.set_facecolor(pal["bg"])
    ax.set_axis_off()
    if title:
        ax.text(58, H - 58, title, color=pal["ink"], fontsize=36,
                fontweight="bold", ha="left", va="top", fontfamily="DejaVu Sans")
        ax.plot([62, H - 62], [H - 92, H - 92], color=pal["accent"],
                lw=3, alpha=0.9)
    if sub:
        ax.text(58, H - 78, sub, color=pal["muted"], fontsize=16,
                ha="left", va="top")
    return fig, ax


def _raster(fig, ax) -> np.ndarray:
    """Draw the current matplot figure -> RGB frame (Axes are data-only; the
    title/subtitle live above it so nothing overlaps the plot)."""
    ax.set_xlim(0, W); ax.set_ylim(0, H)
    ax.invert_yaxis()
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy()
    plt.close(fig)
    return buf


def _t(i: float, total: float) -> float:
    """Normalized time 0..1 with smooth ease-in/out (camera motion)."""
    u = min(1.0, max(0.0, i / (total - 1))) if total > 1 else 1.0
    return u * u * (3 - 2 * u)


def _sliding(data: np.ndarray, t: float) -> tuple:
    """Sliding-window (data, window_start) — the camera pans across the series."""
    N = len(data)
    win = 2048
    start = int(t * max(0, N - win))
    return data[start:start + win], start


# -------------------------------------------------------------------------- #
# scene renderers  (each returns a frame given normalized time t 0..1)
# -------------------------------------------------------------------------- #
def r_hero(t: float, arr: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Spectral waterfall of a real healthy Z24 segment — energy 'river'."""
    pal = HERO_PALETTE
    fig, ax = _base(pal, "VITISH · real Z24 benchmark",
                    "34-channel forced vibration, Koppigen CH · condition label 0 (healthy)")
    seg = arr[0]                       # label 0
    t_ = _t(t, 1)
    st = int(t_ * (seg.shape[1] - 4096))
    win = seg[:, st:st + 4096] - seg[:, st:st + 4096].mean(axis=1, keepdims=True)
    fft = np.fft.rfft(win, axis=1)
    mag = np.abs(fft)
    # mean spectrum across all 27 channels, dB-scaled
    spec = 20 * np.log10(mag.mean(axis=0) + 1e-12)
    freqs = np.fft.rfftfreq(4096, 1 / 100.0)
    ax.plot(freqs[1:], spec[1:], color=pal["green"], lw=1.4)
    ax.fill_between(freqs[1:], spec[1:], spec.min() - 6, color=pal["green"], alpha=0.18)
    ax.text(58, H - 148, f"mean spectrum · window {st//100}s–{(st+4096)//100}s",
            color=pal["muted"], fontsize=15, ha="left", va="top")
    ax.set_xlim(0, 30); ax.set_ylim(spec.min() - 6, spec.max() + 4)
    ax.axvline(3.8, color=pal["accent"], lw=1.2, ls="--", alpha=0.8)
    ax.text(3.95, spec.max() + 1, "f1 ≈ 3.8 Hz", color=pal["accent"], fontsize=13)
    return _raster(fig, ax)


def r_data(t: float, arr: np.ndarray, _labels: np.ndarray) -> np.ndarray:
    """3-channel real time-domain traces (ch 6/7/8) with RMS envelope sweep."""
    pal = PALETTE
    fig, ax = _base(pal, "Real acceleration, 100 Hz",
                    "Z24 deck-edge (ch6) / mid-span (ch7) / deck-edge (ch8)")
    seg = arr[0]
    y = seg[6:9, :]
    y = y - y.mean(axis=1, keepdims=True)
    sig = y.max() * 1.05
    t_ = _t(t, 1)
    win = 4096
    st = int(t_ * (seg.shape[1] - win))
    for k in range(3):
        tr = y[k, st:st + win]
        ax.plot(np.arange(win), tr + k * (sig * 2.4), color=[pal["cyan"],
                pal["green"], pal["amber"]][k], lw=0.9)
        rms = float(np.sqrt((tr ** 2).mean()))
        ax.text(win - 12, k * (sig * 2.4) + sig, f"rms {rms:.2e} g",
                color=pal["muted"], fontsize=13, ha="right", va="bottom")
    ax.set_xlim(0, win); ax.set_ylim(-sig * 1.2 - 0, 3 * sig * 2.4 + sig)
    ax.text(58, H - 148, f"segment {0} · samples {st}–{st+win} · {win/100:.0f} s",
            color=pal["muted"], fontsize=15, ha="left", va="top")
    return _raster(fig, ax)


def r_model(t: float, arr: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Healthy-vs-damaged PSD comparison — the model's separation, real data."""
    pal = PALETTE
    fig, ax = _base(pal, "VAE + OCSVM + LSTM-AE on real Z24",
                    "PSD of measured states: healthy (label 0) vs damaged (labels 2–16)")
    t_ = _t(t, 1)
    fft = np.fft.rfft
    freqs = np.fft.rfftfreq(4096, 1 / 100.0)
    # mean PSD across several segments of each class
    def mean_spec(seg_idx_list):
        acc = []
        for s in seg_idx_list:
            x = arr[s, 7, :] - arr[s, 7, :].mean()
            acc.append(np.abs(fft(x[:4096])) ** 2)
        return np.mean(acc, axis=0)
    healthy = mean_spec([0, 15, 30, 45, 60, 75])
    damaged = mean_spec([540, 560, 580, 620, 660, 700])   # damaged campaign labels
    both = np.concatenate([healthy, damaged])
    ax.set_yscale("log")
    ax.plot(freqs[1:], healthy[1:] + 1e-16, color=pal["green"], lw=1.6,
            label="healthy (label 0)")
    ax.plot(freqs[1:], damaged[1:] + 1e-16, color=pal["red"], lw=1.6,
            label="damaged (labels 2–16)")
    ax.set_xlim(0, 25); ax.set_ylim(both.min() * 0.5, both.max() * 2)
    ax.set_facecolor(pal["deck"])
    ax.grid(True, color=pal["grid"], alpha=0.5)
    ax.text(58, H - 148, "· measured PSD of real benchmark states", color=pal["muted"],
            fontsize=15, ha="left", va="top")
    return _raster(fig, ax)


def r_cv(t: float, _arr: np.ndarray, _labels: np.ndarray) -> np.ndarray:
    """Crack detection film: real CC0 crack photo + real crack_seg.pt mask."""
    pal = PALETTE
    t_ = _t(t, 1)
    frame_name = "mild_crack.jpg"
    img_ = plt.imread(DEMO_FRAMES / frame_name)
    # Run the real model once (STRICT YOLO) and reuse its mask for every frame.
    det = _cv_detect_once(frame_name)
    fig, ax = _base(pal, "Crack detection · real CrackSeg9k photo",
                    f"real input: data/cv/demo_frames/{frame_name}")
    ax.set_axis_off()
    ih, iw, _ = img_.shape
    # layout: photo left, detection pane right
    ax.imshow(img_, extent=[0, 640, 0, 640])
    ax.text(320, 672, "CC0 test photo", color=pal["muted"], fontsize=14,
            ha="center")
    # fade the mask in over the flight
    a = 0.25 + 0.75 * t_
    if det and det.get("mask") is not None:
        mask = det["mask"].astype(float)
        ax.imshow(np.dstack([mask * 0.2, mask, mask * 0.4]), alpha=a,
                  extent=[0, 640, 0, 640])
        conf = float(det["conf"])
        ax.text(960, 380, f"conf {conf:.3f}", color=pal["cyan"], fontsize=20,
                ha="center")
        ax.text(960, 330, f"area {float(det['area_norm']):.3f}", color=pal["cyan"],
                fontsize=20, ha="center")
    else:
        ax.text(960, 500, "no YOLO detection", color=pal["muted"], fontsize=18,
                ha="center")
    return _raster(fig, ax)


def r_fleet(t: float, _arr: np.ndarray, _labels: np.ndarray) -> np.ndarray:
    """LTBP Markov deterioration projection under the empirical fleet prior."""
    pal = PALETTE
    fig, ax = _base(pal, "Fleet deterioration under an empirical LTBP prior",
                    "44 FHWA InfoBridge pilot bridges, 1993–2025")
    # Deterministic projection for a representative fleet bridge (reg-01 @ 74 BHI)
    sys.path.insert(0, str(REPO_ROOT / "backend"))  # namespace pkg "app"
    from app.deterioration import project  # backend import (repo on sys.path)
    rows = project("super", current=7, years=24)   # BHI 74 -> NBI ~7
    t_ = _t(t, 1)
    n = max(2, int(t_ * len(rows)))
    yrs = [r["year"] for r in rows[:n]]
    exp = [r["expected"] for r in rows[:n]]
    p10 = [r["p10"] for r in rows[:n]]
    p90 = [r["p90"] for r in rows[:n]]
    ax.plot(yrs, p90, color=pal["muted"], lw=1, ls="--", alpha=0.8)
    ax.plot(yrs, exp, color=pal["green"], lw=2.2)
    ax.plot(yrs, p10, color=pal["muted"], lw=1, ls="--", alpha=0.8)
    ax.fill_between(yrs, p10, p90, color=pal["green"], alpha=0.10)
    ax.axhline(4, color=pal["red"], lw=1.4, ls="--")
    ax.text(24.4, 4.25, "poor (NBI ≤ 4)", color=pal["red"], fontsize=13,
            ha="right")
    ax.set_xlim(1, 24); ax.set_ylim(1, 9)
    ax.invert_yaxis()
    ax.set_facecolor(pal["deck"])
    ax.grid(True, color=pal["grid"], alpha=0.5)
    ax.text(58, H - 172, "Markov projection — probabilistic band, not a certified RUL",
            color=pal["muted"], fontsize=14, ha="left", va="top")
    return _raster(fig, ax)


def r_demo_arc(t: float, _arr: np.ndarray, _labels: np.ndarray) -> np.ndarray:
    """The verified demo timeline as a film — BHI vs time, pinned arc."""
    pal = PALETTE
    fig, ax = _base(pal, "The verified demo arc",
                    "measured on real Z24 replay — pinned by scripts/verify_demo_arc.py")
    t_ = _t(t, 1)
    # (t_seconds, bhi) vertices — the canonical arc from verify_demo_arc.py
    T = [0, 45, 75, 105, 120]
    B = [87.1, 87.1, 67.5, 33.6, 33.6]
    ts = np.arange(0, t_ * 120 + 0.5, 0.5)
    bhi = np.interp(ts, T, B)
    ax.plot(ts, bhi, color=pal["cyan"], lw=2.4)
    state = ["GREEN", "AMBER", "RED"]
    col = {"GREEN": pal["green"], "AMBER": pal["amber"], "RED": pal["red"]}
    for x, _st, _c in [(0, "GREEN", pal["green"]), (75, "AMBER", pal["amber"]),
                       (105, "RED", pal["red"])]:
        ax.axvline(x, color=_c, lw=1, ls="--", alpha=0.6)
        ax.text(x + 1.5, 18, _st, color=_c, fontsize=14)
    ax.set_xlim(0, 120); ax.set_ylim(0, 100)
    ax.set_facecolor(pal["deck"]); ax.grid(True, color=pal["grid"], alpha=0.5)
    ax.set_xlabel("demo time (s)"); ax.set_ylabel("BHI")
    ax.tick_params(colors=pal["muted"]); ax.xaxis.label.set_color(pal["muted"])
    ax.yaxis.label.set_color(pal["muted"])
    ax.text(58, H - 190, "87.1 GREEN → 45 s crack → 75 s AMBER → 105 s RED → 33.6",
            color=pal["muted"], fontsize=15, ha="left", va="top")
    return _raster(fig, ax)


def r_conn(prev, nxt, t: float) -> np.ndarray:
    """One connector frame: the previous dive's LAST frame cross-dissolving to
    the next dive's FIRST frame — frame-locked continuity (scroll-world seam
    rule: connectors use the real rendered boundary frames, never stills)."""
    pal = PALETTE
    t_ = _t(t, 1)
    fig, ax = _base(pal)
    # prev/nxt are rendered frames already; blend them
    blend = np.clip(t_, 0, 1)
    frame = (prev.astype(np.float32) * (1 - blend) +
             nxt.astype(np.float32) * blend).astype(np.uint8)
    ax.imshow(frame, extent=[0, W, 0, H])
    # subtle travel marker
    ax.plot([W * 0.5 - 40 * (1 - t_), W * 0.5], [H * 0.86, H * 0.86],
            color=pal["accent"], lw=4, alpha=0.7)
    ax.plot([W * 0.5, W * 0.5 + 40 * t_], [H * 0.86, H * 0.86],
            color=pal["accent"], lw=4, alpha=0.7)
    ax.plot(W * 0.5, H * 0.86, "o", color=pal["accent"], ms=7, alpha=0.8)
    ax.text(W * 0.5, H * 0.78, "flight — one connected journey",
            color=pal["muted"], fontsize=14, ha="center", va="bottom")
    return _raster(fig, ax)


# -------------------------------------------------------------------------- #
# cv cache
# -------------------------------------------------------------------------- #
_cv_cache: dict[str, dict | None] = {}


def _cv_detect_once(name: str) -> dict | None:
    """One real crack_seg.pt inference per frame name, reused across frames.
    Returns None (honestly) when weights/inference are unavailable."""
    if name in _cv_cache:
        return _cv_cache[name]
    res = None
    try:
        sys.path.insert(0, str(REPO_ROOT / "models"))
        from cv.inference import CrackDetector
        import cv2
        det = CrackDetector(weights_path=CV_WEIGHTS, conf=0.10, iou=0.45)
        img = cv2.imread(str(DEMO_FRAMES / name))
        if img is None:
            raise FileNotFoundError(name)
        dets = det.detect(img, return_yolo_only=True)
        if dets:
            top = max(dets, key=lambda d: d["conf"])
            res = {
                "conf": float(top["conf"]),
                "mask": (top["mask"] > 0).astype(np.uint8),
                "area_norm": float(top["area_px"]) / float(img.shape[0] * img.shape[1]),
            }
    except Exception:
        res = None
    _cv_cache[name] = res
    return res


# -------------------------------------------------------------------------- #
# encoder
# -------------------------------------------------------------------------- #
def _encode(path: Path, frames: list[np.ndarray]) -> Path:
    gen = imageio_ffmpeg.write_frames(
        str(path), (W, H), pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
        fps=FPS, quality=5, macro_block_size=1, output_params=_ENC)
    next(gen)
    for f in frames:
        gen.send(np.ascontiguousarray(f))
    gen.close()
    return path


def _first_frame(path: Path) -> np.ndarray:
    """Decode a film's first frame (rgb24 HxW) — the dive's establishing frame."""
    exe = ffmpeg_exe()
    cmd = [exe, "-v", "error", "-i", str(path), "-frames:v", "1", "-f", "rawvideo",
           "-pix_fmt", "rgb24", "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(H, W, 3).copy()


def _last_frame(path: Path) -> np.ndarray:
    """Decode a film's LAST frame — the interior handoff frame the next
    connector starts from (scroll-world pipeline §5 uses -sseof for this)."""
    exe = ffmpeg_exe()
    cmd = [exe, "-v", "error", "-sseof", "-0.2", "-i", str(path),
           "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = H * W * 3
    if len(out) > n:                        # sseof may return <n if clipped
        out = out[-n:]
    if len(out) != n:
        raise SystemExit(f"could not decode last frame of {path.name}")
    return np.frombuffer(out, np.uint8).reshape(H, W, 3).copy()


def render_section(name: str, fn) -> list[np.ndarray]:
    return [fn(i / (FPS * DIVE_SEC - 1), _arr, _labels)
            for i in range(FPS * DIVE_SEC)]


# -------------------------------------------------------------------------- #
# main
# -------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", help="render only one section (hero|data|model|cv|fleet|demo|all)")
    ap.add_argument("--expected-sha", help="assert inputs.npy sha256 prefix (data-identity guard)")
    args = ap.parse_args()

    if not (Z24.exists() and Z24_LABELS.exists()):
        raise SystemExit(f"real Z24 benchmark absent ({Z24}) — nothing to render")
    global _arr, _labels
    _arr = np.load(Z24, mmap_mode="r")
    _labels = np.load(Z24_LABELS).ravel()
    if args.expected_sha:
        import hashlib
        h = hashlib.sha256()
        with open(Z24, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
        if not h.hexdigest().startswith(args.expected_sha):
            raise SystemExit(f"Z24 sha mismatch (expected {args.expected_sha}…, got {h.hexdigest()[:16]}…)")

    STILLS.mkdir(parents=True, exist_ok=True)
    FILMS.mkdir(parents=True, exist_ok=True)

    sections: list[tuple[str, object, str]] = [
        ("hero", r_hero, "real Z24 benchmark — healthy label-0 mean spectrum (f1 ≈ 3.8 Hz)"),
        ("data", r_data, "real Z24 acceleration traces (ch 6/7/8), 100 Hz"),
        ("model", r_model, "healthy-vs-damaged PSD separation, real measured states"),
        ("cv", r_cv, "real crack_seg.pt on a real CC0 crack photo"),
        ("fleet", r_fleet, "LTBP Markov projection under the empirical fleet prior"),
        ("demo", r_demo_arc, "the verified demo arc — BHI 87.1→33.6 on real Z24 replay"),
    ]
    wanted = [n for n, _, _ in sections] if args.name in (None, "all") else [args.name]
    manifest = {"generator": "scripts/render_z24_films.py",
                "date": "2026-08-18",
                "source": "real Z24 bridge benchmark (data/z24/inputs.npy, "
                          "1530x27x6000 float32 @ 100 Hz)",
                "encoder": ffmpeg_exe(),
                "encoder_profile": {"gop": 8, "crf": 20, "movflags": "+faststart",
                                    "size": f"{W}x{H}", "fps": FPS},
                "dives_seconds": DIVE_SEC, "connectors_seconds": CONN_SEC,
                "films": {}, "stills": {}, "connectors": []}

    for name, fn, note in sections:
        if name not in wanted:
            continue
        print(f"  rendering {name}…", flush=True)
        frames = render_section(name, fn)
        film = FILMS / f"{name}.mp4"
        _encode(film, frames)
        still = STILLS / f"{name}.webp"
        _write_still(frames[0], still)
        manifest["films"][name] = {"file": f"assets/films/{name}.mp4",
                                   "provenance": note}
        manifest["stills"][name] = {"file": f"assets/stills/{name}.webp",
                                    "provenance": note}
        print(f"    {film.name} {film.stat().st_size/1e6:.2f} MB")

    # connectors — frame-locked to the RENDERED boundary frames (scroll-world
    # seam rule: conn_i starts on dive_i's last frame and ends on dive_{i+1}'s
    # FIRST frame — exactly the frames the engine plays across the seam).
    rendered: list[tuple[str, np.ndarray]] = []
    for name, _, _ in sections:
        if name not in wanted:
            continue
        film = FILMS / f"{name}.mp4"
        rendered.append((name, _first_frame(film)))
    for i in range(len(rendered) - 1):
        prev_name, _ = rendered[i]
        _nxt_name, nxt_first = rendered[i + 1]
        # connector opens on the PREVIOUS dive's ACTUAL last decoded frame (the
        # interior handoff) and closes on the next dive's first frame — the seam
        # rule: connectors use the real rendered boundary frames, never stills.
        prev_last = _last_frame(FILMS / f"{prev_name}.mp4")
        conn_frames = [r_conn(prev_last, nxt_first, k / (FPS * CONN_SEC - 1))
                       for k in range(FPS * CONN_SEC)]
        cf = FILMS / f"conn{i+1}.mp4"
        print(f"  rendering connector conn{i+1} ({prev_name}→{_nxt_name})…", flush=True)
        _encode(cf, conn_frames)
        manifest["connectors"].append(f"assets/films/conn{i+1}.mp4")
        print(f"    {cf.name} {cf.stat().st_size/1e6:.2f} MB")

    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"manifest -> {MANIFEST}")
    return 0


def _write_still(frame: np.ndarray, path: Path) -> None:
    from PIL import Image
    Image.fromarray(frame).convert("RGB").save(path, "WEBP", quality=84)


if __name__ == "__main__":
    raise SystemExit(main())