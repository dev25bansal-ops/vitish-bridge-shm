"""
NEW-02 gate — real site temperature via Open-Meteo, honest offline fallback.

The Koppigen A1 anchor (47.136, 7.578) is fetched from the keyless Open-Meteo
forecast; on ANY network failure the service falls back to the simulated
seasonal day-of-year model and the source label MUST flip so no surface shows
"measured" when the value is modeled.  The measured path is unit-tested with a
faked HTTP client — the suite itself stays network-free
(``VITISH_SITE_TEMP_DISABLE=1`` is exported by scripts/run_tests.sh).

Run:  python backend/tests/test_site_temperature.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import channel_models as cm  # noqa: E402
from app import sim_clock  # noqa: E402
from app import site_temperature as st  # noqa: E402
from app.config import Settings  # noqa: E402
from models.vibration import temperature as thermal  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  [FAIL] {name} {extra}")


FAKE_OK_BODY = b'{"current": {"temperature_2m": 21.3, "time": "2026-08-17T12:00"}}'


class _FakeHttp:
    """Fake HTTP client: returns ``body`` or raises ``exc``; counts calls."""

    def __init__(self, body: bytes | None = None, exc: Exception | None = None):
        self.body = body
        self.exc = exc
        self.calls = 0

    def __call__(self, url: str, timeout_s: float) -> bytes:
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        if self.body is None:
            raise OSError("faked network error")
        return self.body


def test_measured_path() -> None:
    print("[site-temp] measured Open-Meteo path (faked HTTP)")
    st.set_network_disabled(False)
    fake = _FakeHttp(body=FAKE_OK_BODY)
    orig = st._http_get
    st.reset_site_temp_cache()
    st._http_get = fake
    try:
        probe = st.probe_site_temp()
        check("probe temp_c == 21.3", probe["temp_c"] == 21.3, str(probe))
        check("probe source = open-meteo", probe["source"] == st.MEASURED,
              probe["source"])
        check("probe label says measured + Open-Meteo",
              "measured" in probe["source_label"]
              and "Open-Meteo" in probe["source_label"],
              probe["source_label"])
        check("probe not cached yet", probe["cached"] is False)
        check("probe fetched_at stamped", probe["fetched_at"] is not None)

        # caching read: reset the counter so the probe-vs-cache arithmetic is exact
        st.reset_site_temp_cache()
        fake.calls = 0
        first = st.get_site_temp()
        check("get_site_temp measured", first["source"] == st.MEASURED,
              first["source"])
        check("get_site_temp publishes cache", first["cached"] is True)
        second = st.get_site_temp()
        check("second read is served from cache (one fetch)",
              second["cached"] is True and fake.calls == 1,
              f"calls={fake.calls}")

        st.get_site_temp(force_probe=True)
        check("force_probe re-fetches", fake.calls == 2, f"calls={fake.calls}")
    finally:
        st._http_get = orig


def test_fallback_on_error() -> None:
    print("[site-temp] network failure -> simulated fallback + label flip")
    st.set_network_disabled(False)
    fake = _FakeHttp(exc=OSError("connection refused"))
    orig = st._http_get
    st.reset_site_temp_cache()
    sim_clock._reset_t0()
    expected = round(thermal.seasonal_temp_c(sim_clock.day_of_year()), 1)
    st._http_get = fake
    try:
        r = st.get_site_temp()
        check("fallback source = synthetic", r["source"] == st.SYNTHETIC,
              r["source"])
        check("fallback = simulated seasonal temp", abs(r["temp_c"] - expected) < 1e-9,
              f"{r['temp_c']} vs {expected}")
        check("fallback label = simulated, NOT measured",
              "simulated" in r["source_label"]
              and "not a measured sensor" in r["source_label"],
              r["source_label"])
        check("fallback no fetched_at", r["fetched_at"] is None)
        # the flip: the source token is 'synthetic' and the label says the value
        # is the model, never a silent 'measured' claim (it explicitly says
        # 'not a measured sensor' — the honest inverse).
        check("fallback source never claims measured", r["source"] == "synthetic")
    finally:
        st._http_get = orig


def test_garbage_body_never_raises() -> None:
    print("[site-temp] garbage payload -> fallback, never raises")
    st.set_network_disabled(False)
    fake = _FakeHttp(body=b"<html>not json</html>")
    orig = st._http_get
    st.reset_site_temp_cache()
    st._http_get = fake
    try:
        r = st.get_site_temp()
        check("garbage -> synthetic fallback", r["source"] == st.SYNTHETIC,
              str(r))
        check("numeric temp on fallback", isinstance(r["temp_c"], float))
    finally:
        st._http_get = orig


def test_offline_env_forces_fallback() -> None:
    print("[site-temp] VITISH_SITE_TEMP_DISABLE -> zero network")
    st.set_network_disabled(True)
    fake = _FakeHttp()  # would raise OSError if ever called
    orig = st._http_get
    st.reset_site_temp_cache()
    st._http_get = fake
    try:
        r = st.get_site_temp()
        check("disabled -> synthetic", r["source"] == st.SYNTHETIC, r["source"])
        check("http client never invoked", fake.calls == 0, f"calls={fake.calls}")
    finally:
        st._http_get = orig


def test_manifest_block_flip() -> None:
    print("[site-temp] manifest site_temperature block + label flip")
    settings = Settings()
    st.reset_site_temp_cache()

    m_measured = cm.build_manifest(
        settings, "z24-replay", site_temp={
            "site": "Koppigen A1 (47.136, 7.578)",
            "temp_c": 21.3,
            "source": st.MEASURED,
            "source_label": st.MEASURED_LABEL,
            "cached": True,
            "fetched_at": 1_700_000_000.0,
            "note": st._NOTE,
        })
    blk = m_measured.get("site_temperature")
    check("block present when site_temp passed", blk is not None)
    check("measured block source + label",
          blk["source"] == "open-meteo"
          and "measured" in blk["source_label"] and "Open-Meteo" in blk["source_label"],
          str(blk))

    m_fallback = cm.build_manifest(
        settings, "z24-replay", site_temp={
            "site": "Koppigen A1 (47.136, 7.578)",
            "temp_c": 5.2,
            "source": st.SYNTHETIC,
            "source_label": st.SYNTHETIC_LABEL,
            "cached": False,
            "fetched_at": None,
            "note": st._NOTE,
        })
    blk2 = m_fallback.get("site_temperature")
    check("fallback block label = simulated, not measured",
          blk2["source"] == "synthetic"
          and "simulated" in blk2["source_label"]
          and "not a measured sensor" in blk2["source_label"],
          str(blk2))

    m_none = cm.build_manifest(settings, "z24-replay")
    check("no block when site_temp omitted", "site_temperature" not in m_none)
    # a measured site T must never be shown as modeled and vice versa
    check("measured never labeled modeled",
          "simulated" not in blk["source_label"])


def main() -> int:
    try:
        test_measured_path()
        test_fallback_on_error()
        test_garbage_body_never_raises()
        test_offline_env_forces_fallback()
        test_manifest_block_flip()
    except Exception as exc:
        global FAIL
        FAIL += 1
        FAILURES.append("site-temperature tests")
        import traceback
        print(f"  [ERROR] site-temperature tests raised: {exc}")
        traceback.print_exc()
    print()
    print(f"== site-temperature gate: {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())