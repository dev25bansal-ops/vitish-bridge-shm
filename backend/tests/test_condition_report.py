"""COMPREHENSIVE-ANALYSIS item 10 (NEW-04) — IRC-118 / IBMS condition-report
generator tests.

Covers the per-bridge PDF (reportlab) and the fleet IBMS-inventory CSV:
assembly (compose_report labels), hermetic pure PDF bytes (pypdf-extracted
text must carry the DRAFT disclaimer + honesty labels), inventory rows, and the
CSV round-trip with the draft disclaimer on EVERY row.  The suite runs with
VITISH_SITE_TEMP_DISABLE=1 so the site-temperature block is deterministic
(simulated fallback, never a network probe).
"""
import csv
import io
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("VITISH_SITE_TEMP_DISABLE", "1")
_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
for p in (_BACKEND, _REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from fastapi.testclient import TestClient  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from app import condition_report as cr  # noqa: E402
from app import contract  # noqa: E402
from app import regulator_bridges  # noqa: E402

print("[condition-report] IRC-118 PDF + IBMS-inventory CSV generator")
_FAILS = []


def _check(name, cond, detail=""):
    if cond:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name} {detail}")
        _FAILS.append(name)


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


def _hero_fixture():
    return {
        "id": "z24", "name": "Z24 Benchmark Bridge (PS#99 hero)",
        "city": "Koppigen", "state": "BE", "country": "Switzerland",
        "kind": "post-tensioned-concrete-box-girder", "year_built": 1979,
        "length_m": 58, "hero": True,
    }


# --- compose_report -------------------------------------------------------------
reg = next(b for b in regulator_bridges.all_bridges() if b["id"] == "reg-01")
rep = cr.compose_report(reg)
_check("compose regulator: keys", all(k in rep for k in
      ("disclaimer", "bridge", "live", "condition_card", "deterioration",
       "alerts", "site_temp", "generated_at_ms")))
_check("compose regulator: disclaimer", cr.REPORT_DISCLAIMER in rep["disclaimer"])
_check("compose regulator: illustrative label", "illustrative" in (rep["illustrative_note"] or ""))
_check("compose regulator: live flag off",
       rep["bridge"]["hero"] is False and rep["bridge"]["live"] is False)
_check("compose regulator: card from live-cv-subindex",
       rep["condition_card"]["source"] == "live-cv-subindex")
_check("compose regulator: deterioration present",
       rep["deterioration"]["years_to_poor"]["horizon"] == 30)
_check("compose regulator: no alerts", rep["alerts"] == [])
_check("compose regulator: site temp synthetic (env-disabled)",
       rep["site_temp"] is not None
       and rep["site_temp"].get("source") == "synthetic")
_check("compose regulator: noise floor never claims measured",
       "measured" not in str(rep["site_temp"].get("sourceLabel", "")).lower()
       or "not a measured sensor" in rep["site_temp"]["sourceLabel"])

hero_rep = cr.compose_report(
    _hero_fixture(),
    live_state={"bhi": 67.5, "cv": 0.32, "vib": 0.34, "load": 0.40, "u": 3.0,
                "state": "AMBER"},
    alerts=[{"ts": contract.now(), "severity": "warning", "source": "fusion",
             "text": "AMBER bridge health", "recommendation": "inspect"}])
_check("compose hero: live on", hero_rep["bridge"]["hero"] is True
       and hero_rep["bridge"]["live"] is True)
_check("compose hero: alerts carried", len(hero_rep["alerts"]) == 1
       and hero_rep["alerts"][0]["severity"] == "warning")
_check("compose hero: no illustrative label", hero_rep["illustrative_note"] is None)

# --- pdf_bytes (hermetic, no I/O) -----------------------------------------------
pdf = cr.pdf_bytes(hero_rep)
_check("pdf magic header", pdf.startswith(b"%PDF"))
text = _pdf_text(pdf)
for needle in ("Bridge Condition Report", "Z24 Benchmark Bridge",
               "DRAFT in IRC-118 format", "Not a certified assessment",
               "Markov projection", "NBI", "67.5"):
    _check(f"pdf contains {needle!r}", needle in text)
_check("pdf next-inspection section", "inspection" in text.lower())
_check("pdf site-temp section (display only)", "Site temperature" in text)
_check("pdf honesty footer", "model assumption, not an inspection" in text)

reg_pdf = cr.pdf_bytes(rep)
reg_text = _pdf_text(reg_pdf)
_check("regulator pdf carries illustrative caveat",
       "SEEDED/illustrative" in reg_text)
_check("regulator pdf never claims hero", "LIVE — streaming" not in reg_text)

# --- inventory CSV ----------------------------------------------------------------
rows = cr.inventory_rows(regulator_bridges.all_bridges())
_check("inventory: 50 rows", len(rows) == 50, str(len(rows)))
_check("inventory: every row has the disclaimer",
       all(r["record_disclaimer"] == cr.REPORT_DISCLAIMER for r in rows))
_check("inventory: hero row live", next(r for r in rows
      if r["bridge_id"] == "z24")["condition_word"] == "live")
_check("inventory: numeric BHI everywhere",
       all(isinstance(r["bhi"], float) for r in rows))
_check("inventory: NBI within 0..9",
       all(0 <= r["condition_rating_nbi"] <= 9 for r in rows))

csv_text = cr.to_csv(rows)
parsed = list(csv.DictReader(io.StringIO(csv_text.encode("utf-8").decode("utf-8-sig"))))
_check("csv round-trip: 50 records", len(parsed) == 50, str(len(parsed)))
_check("csv header names",
       {"bridge_id", "condition_rating_nbi", "next_inspection_year",
        "record_disclaimer"}.issubset(parsed[0].keys()))
_check("csv disclaimer survives export",
       all(r["record_disclaimer"] == cr.REPORT_DISCLAIMER for r in parsed))

# --- routes (in-process app, deterministic offline) ------------------------------
from app.config import Settings  # noqa: E402
from app import db  # noqa: E402
from dataclasses import replace  # noqa: E402
from app.api import create_app  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="vitish-report-test-")
cfg = replace(Settings(), state_cache_path=Path(_tmp) / "state.jsonl")
db.reset_store()
db.get_store(cfg, prefer="memory")
client = TestClient(create_app())

r = client.get("/api/bridge/reg-01/report.pdf")
_check("route pdf 200", r.status_code == 200, str(r.status_code))
_check("route pdf media + disposition",
       r.headers.get("content-type", "").startswith("application/pdf")
       and "reg-01-condition-report.pdf" in r.headers.get("content-disposition", ""))
_check("route pdf is pdf", r.content.startswith(b"%PDF"))
route_text = _pdf_text(r.content)
_check("route pdf draft label", "IRC-118" in route_text or "DRAFT" in route_text)

r2 = client.get("/api/fleet/report.csv")
_check("route csv 200", r2.status_code == 200, str(r2.status_code))
csv_rows = list(csv.DictReader(io.StringIO(r2.content.decode("utf-8-sig"))))
_check("route csv 50 bridges", len(csv_rows) == 50, str(len(csv_rows)))
_check("route csv disclaimer", all("IRC-118" in x["record_disclaimer"]
      for x in csv_rows))

r3 = client.get("/api/bridge/zz-fake/report.pdf")
_check("route pdf 404 unknown", r3.status_code == 404)

print()
if _FAILS:
    print(f"!! {len(_FAILS)} condition-report check(s) FAILED: {_FAILS}")
    sys.exit(1)
print("== condition-report: ALL PASS ==")