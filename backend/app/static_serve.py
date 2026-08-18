"""
VITISH 2026 · PS#99 SHM — static mounts for the public demo (item 20).

The backend can serve two static sites directly, so a single ``python
backend/app/run_all.py`` process is the whole public demo:

    /        -> landing/           (scroll-world fly-through, item 20)
    /twin    -> twin/dist/         (the digital-twin SPA, built by `npm run build`)

Both mounts are opt-in no-ops when their directory (or the built SPA) is
absent — a source checkout with no ``twin/dist`` is byte-identical to before.

Ordering: the landing is mounted at ``/`` AFTER every explicit route
(``/api/*``, ``/ws``, ``/health`` …) is registered, so Starlette's route order
keeps the real stack first and ``/`` falls through to the static mount.  The
twin SPA is mounted under ``/twin`` with ``html=True`` (its own ``index.html``
serves the SPA; client-side routing inside the SPA is the app's concern).

Sec-notes (applies to a hosted deployment):
  * Nothing here widens the SEC posture — the API still binds loopback unless
    ``VITISH_API_HOST`` says otherwise, WS origin checks still apply, and the
    state-changing demo route still needs ``VITISH_DEMO_TOKEN``.  The static
    mounts only add read-only GET content.
  * The landing's provenance panel reads ``landing/assets/manifest.json`` —
    a static asset, served verbatim (the renderer owns its honesty labels).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI

log = logging.getLogger(__name__)

LANDING_DIR = PROJECT_ROOT / "landing"
TWIN_DIST_DIR = PROJECT_ROOT / "twin" / "dist"


def _mount(app: "FastAPI", path: str, directory: Path) -> bool:
    """Mount a static directory; returns False (no-op) when it has no index."""
    if not (directory / "index.html").exists():
        return False
    app.mount(path, StaticFiles(directory=str(directory), html=True),
              name=f"static:{directory.name}")
    log.info("static mount: %s -> %s", path, directory)
    return True


def install_static(app: "FastAPI") -> dict:
    """Mount twin (``/twin``) and landing (``/``).  Call AFTER all explicit
    routes so route-order keeps /api, /ws, /health first.

    Returns a status dict (also mirrored at /api/config for the twin).
    """
    mounted = {
        "twin": _mount(app, "/twin", TWIN_DIST_DIR),
        "landing": _mount(app, "/", LANDING_DIR),
    }
    log.info("static mounts: twin=%s landing=%s", mounted["twin"], mounted["landing"])
    return mounted
