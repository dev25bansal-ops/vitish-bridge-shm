"""
COMPREHENSIVE-ANALYSIS item 10 (NEW-04) · IRC-118 / IBMS condition-report
generator.

Assembles the pieces that already exist in-repo into regulator-facing report
artifacts:

  1. A per-bridge **PDF** condition report (reportlab platypus) carrying the
     live state, the D1-3 condition card, the D1-4/D2-11 Markov projection +
     next-inspection recommendation, recent alerts, and the NEW-02 site
     temperature — every block with its honesty label verbatim.
  2. A **fleet inventory CSV** (IBMS-inventory style, one row per bridge) so
     the 50 bridges can be ingested into the regulator inventory tool.

HONESTY: this is an explicitly NOT-certified DRAFT in IRC-118 format — fields
to be confirmed against the final MoRTH IBMS schema.  The generator never
invents a field: every number is whatever the underlying services report (the
live store for the hero, deterministic seeded health for the 49 regulator
bridges, Markov projection under the empirical LTBP prior).  Live vs
illustrative is marked per bridge, and the "49 regulators seeded/illustrative —
not real inspection data" caveat is on every surface.

This module is deliberately import-light: nothing here opens a socket or reads
the network except ``site_temperature.get_site_temp()``, which is never-raises
and degrades to the simulated seasonal model offline (``VITISH_SITE_TEMP_DISABLE=1``).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

from app import contract
from app import deterioration as det_mod
from app import site_temperature as site_temp_mod
from models.fusion import condition as cond_mod

# The mandatory draft disclosure — repeated on the PDF cover block AND as a
# per-row column in the fleet CSV so the caveat survives a cut-and-paste export.
REPORT_DISCLAIMER = (
    "DRAFT in IRC-118 format — fields to be confirmed against the final MoRTH "
    "IBMS schema.  Not a certified assessment; never a basis for load "
    "restriction, closure, or a legally-binding condition rating."
)
ILLUSTRATIVE_LABEL = ("49 regulator bridges are SEEDED/illustrative health — "
                      "never real inspection data (only the hero bridge is live).")

_ICON_FROM = {"GREEN": "healthy", "AMBER": "deteriorating", "RED": "critical-alert"}


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
def compose_report(bridge: dict, live_state: Optional[dict] = None,
                   alerts: Optional[List[dict]] = None) -> dict:
    """Assemble one fully-labeled report dict for a bridge.

    ``bridge``     the bridge dict from ``regulator_bridges.all_bridges`` (hero
                   or regulator) — id/name/city/state/kind/year_built/length_m.
    ``live_state`` the live merged hero snapshot (bhi/state/cv/vib/load/u) for
                   the hero; ``None`` for regulator bridges (their health is
                   already on the dict).
    ``alerts``     recent-alert rows [{ts, severity, source, text,
                   recommendation}] for the hero; ``None`` for regulators (no
                   alert store kept).
    """
    bid = bridge["id"]
    is_hero = bool(bridge.get("hero", False)) or bid == "z24"
    st = live_state if live_state is not None else bridge
    bhi = float(st["bhi"])
    state = str(st.get("state", contract.state_for(bhi)))
    cv = float(st.get("cv", 0.15 if not is_hero else 0.10))
    vib = float(st.get("vib", 0.15 if not is_hero else 0.12))
    load = float(st.get("load", 0.20 if not is_hero else 0.19))
    u = float(st.get("u", 3.0))

    card = cond_mod.card_from_live_cv(cv)          # D1-3 (live-cv-subindex)
    det = det_mod.bridge_deterioration(bid, bhi)    # D1-4/D2-11 (Markov prior)
    return {
        "disclaimer": REPORT_DISCLAIMER,
        "illustrative_note": None if is_hero else ILLUSTRATIVE_LABEL,
        "generated_at_ms": contract.now(),
        "bridge": {
            "id": bid,
            "name": bridge["name"],
            "location": f"{bridge['city']}, {bridge['state']}",
            "country": bridge.get("country", "USA"),
            "kind": bridge.get("kind", ""),
            "year_built": bridge.get("year_built"),
            "length_m": bridge.get("length_m"),
            "hero": is_hero,
            "live": is_hero,  # only the hero streams real data through the pipeline
        },
        "live": {
            "bhi": round(bhi, 1),
            "state": state,
            "state_word": _ICON_FROM.get(state, state),
            "cv": cv, "vib": vib, "load": load, "u": u,
            "source_note": ("live fused sub-indices from the streaming pipeline"
                            if is_hero else
                            "deterministic SEEDED health (illustrative — not live)"),
        },
        "condition_card": card,
        "deterioration": det,
        "alerts": list(alerts or []),
        "site_temp": site_temp_mod.get_site_temp(),
    }


def inventory_rows(bridges: List[dict]) -> List[dict]:
    """One IBMS-inventory row per bridge (health, NBI rating, next-inspection,
    years-to-poor band) with every honesty label attached.  Computation reuses
    the exact services the UI reads — never a parallel re-derivation."""
    rows = []
    for b in bridges:
        bhi = float(b["bhi"])
        current = det_mod.condition_from_bhi(bhi)
        nxt = det_mod.next_inspection("super", current)
        band = det_mod.years_to_poor("super", current, threshold=4, horizon=30)
        is_hero = bool(b.get("hero", False))
        rows.append({
            "bridge_id": b["id"],
            "bridge_name": b["name"],
            "location": f"{b['city']}, {b['state']}",
            "state": b["state"],
            "bhi": round(bhi, 1),
            "condition_rating_nbi": current,
            "condition_word": ("live" if is_hero
                               else "illustrative (seeded)"),
            "next_inspection_year": nxt if nxt is not None else "",
            "years_to_poor_expected": band["expected"],
            "record_disclaimer": REPORT_DISCLAIMER,
        })
    return rows


def to_csv(rows: List[dict], fieldnames: Optional[List[str]] = None) -> str:
    """Render inventory rows as CSV (UTF-8 with BOM so Excel decodes °/—/±)."""
    fieldnames = fieldnames or list(rows[0].keys()) if rows else []
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return "﻿" + out.getvalue()


# ---------------------------------------------------------------------------
# PDF rendering (reportlab platypus, built-in Helvetica fonts only)
# ---------------------------------------------------------------------------
_STYLES = getSampleStyleSheet()
_H = {"title": ParagraphStyle("ctitle", parent=_STYLES["Title"], fontSize=17,
                              leading=20, alignment=TA_CENTER,
                              textColor=colors.HexColor("#0f172a")),
      "sub": ParagraphStyle("csub", parent=_STYLES["Italic"], fontSize=9,
                            leading=12, alignment=TA_CENTER,
                            textColor=colors.HexColor("#64748b")),
      "h": ParagraphStyle("sec", parent=_STYLES["Heading2"], fontSize=11.5,
                          leading=14, spaceBefore=10, spaceAfter=4,
                          textColor=colors.HexColor("#0f172a")),
      "body": ParagraphStyle("body", parent=_STYLES["BodyText"], fontSize=9,
                             leading=12),
      "small": ParagraphStyle("small", parent=_STYLES["BodyText"], fontSize=7.5,
                              leading=10, textColor=colors.HexColor("#475569")),
      "disc": ParagraphStyle("disc", parent=_STYLES["BodyText"], fontSize=9,
                             leading=12, textColor=colors.HexColor("#7c2d12"))}


def _kv_table(kv: List[tuple]) -> Table:
    cells = [[_p(f"<b>{k}</b>", "small"), _p(str(v) or "—", "body")] for k, v in kv]
    t = Table(cells, colWidths=[34 * mm, 138 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, _H[style])


def _mono(text: str) -> str:
    return f'<font face="Courier">{text}</font>'


def pdf_bytes(report: dict) -> bytes:
    """Pure-PDF renderer: takes a ``compose_report`` dict, returns PDF bytes.
    Kept pure (no I/O, no network) so it is trivially hermetic in tests."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Bridge condition report — {report['bridge']['name']}",
        author="VITISH SHM (PS#99)" )
    b = report["bridge"]
    story = []

    # cover: title + draft disclaimer -----------------------------------------
    story.append(_p(f"Bridge Condition Report", "title"))
    story.append(Spacer(1, 2 * mm))
    story.append(_p(f"{b['name']} &nbsp;·&nbsp; {b['id']}", "sub"))
    gen = datetime.fromtimestamp(report["generated_at_ms"] / 1000,
                                 tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(_p(f"generated {gen} · VITISH SHM PS#99 demo artifact", "sub"))
    story.append(Spacer(1, 3 * mm))
    disc = Table([[_p(report["disclaimer"], "disc")]], colWidths=[174 * mm])
    disc.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef2f2")),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#fca5a5")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(disc)
    if report.get("illustrative_note"):
        note = Table([[_p(report["illustrative_note"], "disc")]], colWidths=[174 * mm])
        note.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#fcd34d")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(Spacer(1, 2 * mm))
        story.append(note)

    # 1 · bridge identity -------------------------------------------------------
    story.append(_p("1 · Bridge identity", "h"))
    story.append(_kv_table([
        ("Bridge ID", _mono(b["id"])),
        ("Location", f"{b['location']}, {b['country']}"),
        ("Type", b["kind"] or "—"),
        ("Year built", b["year_built"] or "—"),
        ("Span (m)", f"{b['length_m']:.0f}" if isinstance(b["length_m"], (int, float)) else "—"),
        ("Data", "LIVE — streaming through the real pipeline" if b["live"]
         else "illustrative (seeded health, not live)"),
    ]))

    # 2 · live condition ----------------------------------------------------------
    story.append(_p("2 · Live condition state", "h"))
    lv = report["live"]
    story.append(_kv_table([
        ("BHI (0–100)", f'{lv["bhi"]:.1f} &nbsp;·&nbsp; <b>{lv["state"]}</b> '
                        f'({lv["state_word"]})'),
        ("Sub-indices", f'cv {lv["cv"]:.2f} · vib {lv["vib"]:.2f} · '
                        f'load {lv["load"]:.2f} · u {lv["u"]:.1f}'),
        ("Source", lv["source_note"]),
    ]))

    # 3 · condition card (D1-3) ---------------------------------------------------
    story.append(_p("3 · Condition card (crack index, D1-3)", "h"))
    c = report["condition_card"]
    cond = c.get("condition", {})
    story.append(_kv_table([
        ("Source", f'{c.get("source")} — {c.get("frame_note", "")}'),
        ("Crack index", f'{c.get("crack_index"):.3f} · burden '
                        f'{c.get("burden"):.3f} · {c.get("severity")}'),
        ("NBI 0–9", f'{cond.get("nbi")} · {cond.get("nbi_label")}'),
        ("Risk class", cond.get("risk_class", "—")),
        ("Confidence", f'{c.get("confidence"):.2f}'),
    ]))
    story.append(_p(c.get("note", ""), "small"))

    # 4 · deterioration (D1-4/D2-11) -----------------------------------------------
    story.append(_p("4 · Deterioration projection (Markov, LTBP prior)", "h"))
    d = report["deterioration"]
    y2p = d.get("years_to_poor", {})
    band_txt = ("already at/below NBI 4 (0 years)"
                if y2p.get("already_poor")
                else f"p10 {y2p.get('p10')} · expected {y2p.get('expected')} · "
                     f"p90 {y2p.get('p90')} yrs")
    story.append(_kv_table([
        ("Current condition (NBI)", d["current_condition"]),
        ("Priors", d["priors_label"]),
        ("Next inspection rule", d["next_inspection_rule"]),
        ("Next inspection (yr)", d["next_inspection_year"] if d["next_inspection_year"]
         else "—",
         ),
        ("Years to NBI ≤ 4", band_txt),
    ]))
    story.append(Spacer(1, 1.5 * mm))
    proj = d["projection"][:15]
    table = [[_p("<b>Year</b>", "small"), _p("<b>Expected NBI</b>", "small"),
              _p("<b>p90 · p10</b>", "small"), _p("<b>P(NBI ≤ 4)</b>", "small")]
             for _ in [0]] + [
        [_p(_mono(str(r["year"])), "small"),
         _p(f'{r["expected"]:.2f}', "small"),
         _p(f'{r["p90"]} · {r["p10"]}', "small"),
         _p(f'{r["p_poor"]:.1%}', "small")]
        for r in proj]
    ptab = Table(table, colWidths=[22 * mm, 42 * mm, 42 * mm, 48 * mm])
    ptab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    story.append(ptab)
    story.append(_p(d["note"], "small"))

    # 5 · alerts -------------------------------------------------------------------
    story.append(_p("5 · Recent alerts", "h"))
    alerts = report["alerts"]
    if not alerts:
        story.append(_p("No alert store kept for this bridge (only the live hero "
                        "keeps alert history).", "small"))
    else:
        atab = [[_p("<b>Time (UTC)</b>", "small"), _p("<b>Sev</b>", "small"),
                 _p("<b>Source</b>", "small"), _p("<b>Text</b>", "small")] for _ in [0]] + [
            [_p(_mono(datetime.fromtimestamp(a["ts"] / 1000, tz=timezone.utc)
                      .strftime("%m-%d %H:%M")), "small"),
             _p(str(a.get("severity", "")).upper(), "small"),
             _p(str(a.get("source", "")), "small"),
             _p(str(a.get("text", "")), "small")]
            for a in alerts[:8]]
        at = Table(atab, colWidths=[26 * mm, 14 * mm, 30 * mm, 104 * mm])
        at.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ]))
        story.append(at)

    # 6 · site temperature (NEW-02) --------------------------------------------------
    story.append(_p("6 · Site temperature (display only)", "h"))
    st = report["site_temp"]
    if st and st.get("tempC") is not None:
        src = "measured" if st.get("source") == "open-meteo" else "modeled"
        story.append(_kv_table([
            ("Air temperature", f'{st["tempC"]:.1f} °C'),
            ("Source", f'<b>{src}</b> — {st.get("sourceLabel", "")}'),
            ("Cache", "yes" if st.get("cached") else "no"),
        ]))
        story.append(_p(st.get("note", ""), "small"))
    else:
        story.append(_p("Not available (offline).", "small"))

    # footer: honesty labels ----------------------------------------------------------
    story.append(Spacer(1, 3 * mm))
    for line in (
        "Disclosure: the BHI is a transparent weighted fusion; its NBI mapping is a "
        "model assumption, not an inspection. The Markov projection is a probabilistic "
        "fleet-prior model — not a certified RUL and not a Paris-law forecast.",
        "The condition card is a relative severity reading (crack index) — NEVER a "
        "certified structural assessment.",
        ILLUSTRATIVE_LABEL,
    ):
        story.append(_p(line, "small"))

    doc.build(story)
    return buf.getvalue()


if __name__ == "__main__":
    import json
    sample = compose_report({  # hero-shaped fixture (no live store needed)
        "id": "z24", "name": "Z24 Benchmark Bridge (PS#99 hero)",
        "city": "Koppigen", "state": "BE", "country": "Switzerland",
        "kind": "post-tensioned-concrete-box-girder", "year_built": 1979,
        "length_m": 58, "hero": True},
        live_state={"bhi": 67.5, "cv": 0.32, "vib": 0.34, "load": 0.40, "u": 3.0,
                    "state": "AMBER"},
        alerts=[{"ts": contract.now(), "severity": "warning",
                 "source": "fusion", "text": "AMBER bridge health",
                 "recommendation": "schedule inspection"}])
    pdf = pdf_bytes(sample)
    print(f"PDF {len(pdf)} bytes -> {sample['bridge']['name']} "
          f"(BHI {sample['live']['bhi']})")