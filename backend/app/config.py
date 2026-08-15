"""
VITISH 2026 · PS#99 SHM — configuration.

A single dataclass ``Settings`` that every component reads.  Values are
overridable through environment variables (``VITISH_*``) and a local ``.env``
file.  Sane defaults keep the whole stack working with zero configuration:
MQTT at localhost:1883, WebSocket at 8765, API at 8000, Postgres DSN pointing
at the docker-compose database (optional — the store auto-falls back to an
in-memory store when Postgres is unreachable).
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]   # .../backend
PROJECT_ROOT = BACKEND_DIR.parent                    # repo root

# make backend/ and repo root importable regardless of cwd (see app/__init__)
for _p in (BACKEND_DIR, PROJECT_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from app import contract  # noqa: E402  (authoritative schema, read-only)

# --- .env discovery (first match wins) --------------------------------------
for _env_file in (
    PROJECT_ROOT / ".env",
    BACKEND_DIR / ".env",
    BACKEND_DIR / "app" / ".env",
):
    if _env_file.exists():
        load_dotenv(_env_file, override=False)
        break


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    try:
        return int(v) if v else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    try:
        return float(v) if v else default
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if not v:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _env_list_int(name: str, default: List[int]) -> List[int]:
    v = os.getenv(name)
    if not v:
        return list(default)
    # guard: a non-integer node id (e.g. "6,7,eight") must not crash config
    # loading — fall back to the default list instead of raising (item 11).
    try:
        return [int(x) for x in v.split(",") if x.strip()]
    except ValueError:
        return list(default)


@dataclass
class Settings:
    # --- bridge / nodes ------------------------------------------------------
    bridge_id: str = contract.BRIDGE_ID                       # "z24"
    nodes: List[int] = field(default_factory=lambda: list(contract.Z24_SIM_NODES))  # [6,7,8]

    # --- MQTT broker ---------------------------------------------------------
    broker_host: str = "localhost"
    broker_port: int = 1883
    mqtt_keepalive: int = 60

    # --- services ------------------------------------------------------------
    ws_host: str = "0.0.0.0"
    ws_port: int = 8765
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- persistence ---------------------------------------------------------
    # No default credential (ROADMAP line 92): Postgres is opt-in via the
    # VITISH_DB_DSN env var.  Empty db_dsn -> MemoryStore (get_store guards it);
    # the demo runs on MemoryStore anyway.
    db_dsn: str = ""
    state_cache_path: Path = BACKEND_DIR / "app" / "state_cache.json"

    # --- data / models -------------------------------------------------------
    data_dir: Path = PROJECT_ROOT / "data" / "z24"
    model_dir: Path = PROJECT_ROOT / "models"
    weights_path: Path = PROJECT_ROOT / "models" / "weights"

    # --- sampling & inference (mirrors contract) -----------------------------
    fs: int = contract.FS_ACCEL
    window_n: int = contract.WINDOW_N
    window_s: float = contract.WINDOW_S

    # --- device-level anomaly flag -------------------------------------------
    # flag = 1 when rms > max(flag_factor * rolling_rms_baseline, flag_floor)
    accel_flag_factor: float = 2.5
    accel_flag_floor: float = 0.15

    # --- BHI fusion defaults -------------------------------------------------
    # Baseline 87: 100*(1 - 0.40*0.10 - 0.35*0.12 - 0.25*0.19) = 87.05
    cv_default: float = 0.10
    load_default: float = 0.19
    vib_base: float = 0.12
    bhi_publish_interval: float = 1.0

    # --- damage injector -----------------------------------------------------
    ramp_s: float = 10.0     # smooth healthy->rupture fade (s)
    impact_s: float = 2.5    # broadband 'tendon snap' burst (s) on rupture onset
    impact_amp: float = 0.8

    # --- demo driver ---------------------------------------------------------
    demo_speed: float = 1.0

    # --- misc ----------------------------------------------------------------
    log_level: str = "INFO"
    version: str = "0.1.0"

    def accel_topic(self) -> str:
        return contract.TOPIC_ACCEL.format(bridge=self.bridge_id)

    def bhi_topic(self) -> str:
        return contract.TOPIC_BHI.format(bridge=self.bridge_id)

    def alert_topic(self) -> str:
        return contract.TOPIC_ALERT.format(bridge=self.bridge_id)

    def status_topic(self) -> str:
        return contract.TOPIC_STATUS.format(bridge=self.bridge_id)

    def frame_topic(self) -> str:
        return contract.TOPIC_FRAME.format(bridge=self.bridge_id)


def load_settings() -> Settings:
    s = Settings(
        bridge_id=_env_str("VITISH_BRIDGE_ID", contract.BRIDGE_ID),
        nodes=_env_list_int("VITISH_NODES", contract.Z24_SIM_NODES),
        broker_host=_env_str("VITISH_MQTT_HOST", "localhost"),
        broker_port=_env_int("VITISH_MQTT_PORT", 1883),
        ws_host=_env_str("VITISH_WS_HOST", "0.0.0.0"),
        ws_port=_env_int("VITISH_WS_PORT", 8765),
        api_host=_env_str("VITISH_API_HOST", "0.0.0.0"),
        api_port=_env_int("VITISH_API_PORT", 8000),
        db_dsn=_env_str("VITISH_DB_DSN", ""),
        accel_flag_factor=_env_float("VITISH_ACCEL_FLAG_FACTOR", 2.5),
        accel_flag_floor=_env_float("VITISH_ACCEL_FLAG_FLOOR", 0.15),
        cv_default=_env_float("VITISH_CV_DEFAULT", 0.10),
        load_default=_env_float("VITISH_LOAD_DEFAULT", 0.19),
        vib_base=_env_float("VITISH_VIB_BASE", 0.12),
        ramp_s=_env_float("VITISH_RAMP_S", 10.0),
        log_level=_env_str("VITISH_LOG_LEVEL", "INFO"),
    )
    data_dir = _env_str("VITISH_DATA_DIR", "")
    if data_dir:
        s.data_dir = Path(data_dir)
    models_dir = _env_str("VITISH_MODELS_DIR", "")
    if models_dir:
        s.model_dir = Path(models_dir)
        s.weights_path = Path(models_dir) / "weights"
    return s


# module-level singleton — every component shares one immutable-ish config
settings = load_settings()


def setup_logging(level: str | None = None) -> None:
    lvl = (level or settings.log_level).upper()
    logging.basicConfig(
        level=getattr(logging, lvl, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
