"""§7.6 item 20 gate — hosted public demo + cinematic landing (deterministic).

Pins the item-20 deliverables WITHOUT any build step, network, or Postgres:

  * static mounts — backend/app/static_serve.py mounts twin/dist under /twin and
    landing/ under / (opt-in no-ops when absent); api.py calls install_static()
    LAST and /api/health still answers through the mount wiring (TestClient).
  * cinematic landing — every landing asset the index.html references exists and
    the hero-scrub film is a decode-valid h264 (1280x720, 24 fps); the page
    carries the honest-film provenance note (Film: real Z24 ... not raw
    telemetry), the derived demonstrator copy stays aligned (CrackSeg9k, 24/24
    gates, /twin CTA, NOT-a-real-dispatch honesty), and all 10 sections exist.
  * recipe SEC posture — deploy/hosted-demo/.env.public.example has broker
    creds + demo token + pinned origins + VITE_WS_URL=wss://; the Caddyfile is
    a plain reverse_proxy to 127.0.0.1:8000; the example .env is gitignored.
  * origin-aware twin — twin/vite.config.ts uses base './' (relative assets so
    /twin works under the mount) and twin/src/lib/config.ts falls back to
    same-origin /api + /ws for non-localhost (source-inspection, mirroring the
    live-feed cred test).

Run:  python backend/tests/test_hosted_demo.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import imageio_ffmpeg  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import static_serve  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []

LANDING = ROOT / "landing"
HERO_FILM = LANDING / "assets" / "hero-scrub.mp4"
TWIN = ROOT / "twin"
DEPLOY = ROOT / "deploy" / "hosted-demo"

EXPECTED_SECTIONS = [
    "provenance", "thermal", "multimodal", "twin", "countdown",
    "developer-cta", "architecture", "economics", "faq", "pilot-request",
]
# Every asset the landing index.html references (single quotes keep it tight).
REQUIRED_ASSET_FRAGMENTS = [
    "assets/hero-scrub.mp4",
    "assets/hero-poster.jpg",
    "assets/section-provenance.webp",
    "assets/section-thermal.webp",
    "assets/section-multimodal.webp",
    "assets/section-twin.webp",
    "assets/favicon.svg",
]


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  XX  {name} {detail}")


def mp4_valid(path: Path) -> bool:
    """Decode-validate: h264 1280x720, 24 fps, full null decode without error."""
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        info = subprocess.run([ff, "-i", str(path)], capture_output=True,
                              text=True, timeout=30).stderr
        ok = ("Video: h264" in info and "1280x720" in info and "24 fps" in info
              and "Duration:" in info)
        dec = subprocess.run([ff, "-v", "error", "-i", str(path), "-f", "null", "-"],
                             capture_output=True, text=True, timeout=90)
        return ok and dec.returncode == 0 and dec.stderr.strip() == ""
    except Exception:
        return False


def app_with_mounts(mount: bool) -> FastAPI:
    """A bare app with the same install order as api.py: routes first, then
    install_static() last (the item-20 mount contract)."""
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "static": _s.get("twin", False), "landing": _s.get("landing", False)}

    _s: dict = {}
    if mount:
        _s.update(static_serve.install_static(app))
    return app


def test_static_mounts() -> None:
    print("== static mounts + landing wiring ==")
    # 1. api.py calls install_static() last (after explicit routes, before
    #    returning the app).
    src = (BACKEND / "app" / "api.py").read_text(encoding="utf-8")
    check("api.py calls install_static() before return app",
          "install_static(app)" in src
          and src.index("install_static(app)") < src.index("return app"),
          "(install_static must run before create_app returns)")
    # 2. static_serve is a no-op when twin/dist is absent.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "landing").mkdir()
        (tmp / "landing" / "index.html").write_text("<h1>l</h1>", encoding="utf-8")
        # patch dirs at the module level (they are module constants)
        old_l, old_t = static_serve.LANDING_DIR, static_serve.TWIN_DIST_DIR
        static_serve.LANDING_DIR, static_serve.TWIN_DIST_DIR = tmp / "landing", tmp / "twin-dist"
        try:
            app = FastAPI()

            @app.get("/api/health")
            def h() -> dict:
                return {"ok": True}

            mounts = static_serve.install_static(app)
            check("twin mount no-op without twin/dist", mounts["twin"] is False)
            check("landing mount served", mounts["landing"] is True)
        finally:
            static_serve.LANDING_DIR, static_serve.TWIN_DIST_DIR = old_l, old_t
    # 3. route order: /api/health still 200 through the mount wiring.
    app = app_with_mounts(mount=True)
    with TestClient(app) as c:
        r = c.get("/api/health")
        check("GET /api/health 200 through mounts", r.status_code == 200, str(r.status_code))
        home = c.get("/")
        check("GET / serves the landing index", home.status_code == 200 and "<html" in home.text,
              str(home.status_code))


def test_cinematic_landing() -> None:
    print("== cinematic landing: assets + honesty + derived demonstrator copy ==")
    idx = (LANDING / "index.html").read_text(encoding="utf-8")
    # Every asset the page references actually exists on disk.
    for frag in REQUIRED_ASSET_FRAGMENTS:
        asset = LANDING / frag
        check(f"referenced asset exists {frag}", asset.exists(), str(asset))
    # The hero scrub film is a real decode-valid video with the right contract.
    check("hero-scrub.mp4 exists", HERO_FILM.exists())
    if HERO_FILM.exists():
        check("hero-scrub.mp4 decode-valid (h264 1280x720 24fps)",
              mp4_valid(HERO_FILM), HERO_FILM.name)
    # Honesty: the film is labelled as a dramatisation, not raw telemetry (R1/R3).
    check("hero-film provenance note present", "not raw telemetry" in idx)
    check("honesty footer present", "fictional product name" in idx
          and "Morbi framing is honest" in idx)
    # All 10 below-the-fold sections exist (anchor + heading).
    for sid in EXPECTED_SECTIONS:
        check(f"section #{sid} present", f'id="{sid}"' in idx, sid)
    # Derived demonstrator copy stays aligned with the repo's real state.
    check("segmenter honestly = CrackSeg9k", "CrackSeg9k" in idx
          and "SDNET2018" not in idx)
    check("gate count honest (24/24)", "24/24" in idx and "8/8" not in idx)
    check("twin CTA present", "/twin/" in idx)
    check("demo-arc numbers honest", "BHI 87.1" in idx and "33.6" in idx
          and "3.23 Hz" in idx)
    check("not-a-real-dispatch honesty", "Not a real NHAI dispatch" in idx)


def main() -> int:
    global PASS, FAIL
    try:
        test_static_mounts()
        test_cinematic_landing()
        test_recipe_posture()
        test_twin_origin_aware()
    except Exception as exc:
        FAIL += 1
        FAILURES.append("hosted-demo tests")
        import traceback
        print(f"  [ERROR] hosted-demo tests raised: {exc}")
        traceback.print_exc()
    print()
    print(f"== hosted public demo + cinematic landing gate (item 20): {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 1 if FAIL else 0


def test_recipe_posture() -> None:
    print("== hosted-demo recipe SEC posture ==")
    env = (DEPLOY / ".env.public.example").read_text(encoding="utf-8")
    check(".env.public.example exists", (DEPLOY / ".env.public.example").exists())
    check("broker creds present (SEC-01)", "VITISH_MQTT_USER=vitish" in env
          and "VITISH_MQTT_PASS=" in env)
    check("demo token present (SEC-02)", "VITISH_DEMO_TOKEN=" in env)
    check("origins pinned, not wildcard (SEC-03/06)",
          "VITISH_WS_ORIGINS=https://demo.example.com" in env
          and "VITISH_CORS_ORIGINS=https://demo.example.com" in env
          and "VITISH_WS_ORIGINS=*" not in env)
    check("twin WS URL is wss (public TLS)", "VITE_WS_URL=wss://demo.example.com/ws" in env)
    caddy = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    check("Caddyfile reverse_proxy 127.0.0.1:8000",
          "reverse_proxy 127.0.0.1:8000" in caddy)
    check("Caddyfile is TLS-auto (no bare http://)", "://127.0.0.1" not in caddy)
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    check(".env.public is gitignored", ".env.public" in gi)


def test_twin_origin_aware() -> None:
    print("== origin-aware twin + relative build base ==")
    vite = (TWIN / "vite.config.ts").read_text(encoding="utf-8")
    check("vite base './' (relative assets)", "base: './'" in vite)
    conf = (TWIN / "src" / "lib" / "config.ts").read_text(encoding="utf-8")
    check("config.ts has isLocalhost()", "export function isLocalhost" in conf)
    check("config.ts same-origin /api fallback", "sameOriginApi" in conf
          and "window.location.origin" in conf)
    check("config.ts same-origin /ws fallback", "sameOriginWs" in conf
          and "window.location.host" in conf)
    check("config.ts hosted discovery probes same-origin", "!isLocalhost()" in conf)
    t = (TWIN / "src" / "lib" / "config.test.ts").read_text(encoding="utf-8")
    check("config.test.ts covers same-origin fallback", "same-origin fallback" in t
          and "hosted discovery probes" in t)


if __name__ == "__main__":
    sys.exit(main())
