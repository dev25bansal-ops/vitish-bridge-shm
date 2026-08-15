---
tags: [demo, rehearsal, checklist, vitish-2026, shm]
created: 2026-08-15
---

# Dress-Rehearsal Runbook (venue-class, timed, recorded)

> ROADMAP line 101. Run this at the venue (or any projector+audio room) at least
> once before H0. The story is [[Storyboard]]; the timer is authoritative; the
> fail-injection list is mandatory — a demo that survives its own failure modes
> is the demo. **REMAINING HUMAN ACTION:** schedule the room + 2 recorders.

## Setup (5 min, before the timer starts)

- [ ] Projector + audio checked; laptop on venue WiFi (or offline — RUNBOOK §2)
- [ ] `cd backend && python -m app.run_all --demo` → banner shows API + WS ports
- [ ] `cd twin && npm run dev` → twin loads, WS shows `LIVE · backend ws`
- [ ] Screen recording started (OBS/phone) — **take 1 of 2**
- [ ] `.env` Cesium token present (Geo view optional) or SVG fallback confirmed
- [ ] Phone on a tripod as take 2; stopwatch visible to the operator

## The 6:00 script (from [[Storyboard]], timed beats)

| Time | Beat | Operator |
|---|---|---|
| 0:00–0:15 | Morbi cold-open hook (death toll ~135, [[Verified-Facts]]) | speaker |
| 0:15–1:00 | Problem: inspection gap (170 vs 42, Tocantins 2024) — slide 1–2 | speaker |
| 1:00–2:00 | The twin live: fleet map → hero Z24 → BHI GREEN 87.1, provenance panel | operator clicks |
| 2:00–3:00 | Rupture scenario → AMBER 67.5 → RED 33.6; stiffness overlay + alerts | operator triggers `/api/demo/scenario rupture` |
| 3:00–3:40 | CV: condition card from the real crack segmenter (`?run_seg=1`) | operator |
| 3:40–4:30 | Deterioration + Markov projection; cost slide ($980 / $260/yr / $25–30/mo) | speaker |
| 4:30–5:30 | Roadmap + ask (IBMS 30 Sep 2026, one pilot) — slide 9–10 | speaker |
| 5:30–6:00 | Recovery to GREEN; close | operator |

## Fail-injection (one per run — survive all four across 2 runs)

1. **Broker down** — kill mosquitto (or don't start Docker): demo must keep
   streaming direct-on-bus. Confirm the banner / `/health` still serve.
2. **No internet** — run with `--demo` only (no `--live`); `/api/live` →
   `enabled:false`; twin must not error (warnOnce breadcrumbs only).
3. **8000/8765 occupied** — start a dummy listener on 8000 first; run_all must
   fall back to 8001/8766 and the twin must discover the real ports
   (`/api/config`). Script it: `python -c "import socket,time;s=socket.socket();s.bind(('0.0.0.0',8000));s.listen();time.sleep(60)"`.
4. **Backgrounded tab** — switch the browser tab away mid-rupture and back; the
   twin must resume from the live WS stream (no stale replay), sensors grey-out
   >4 s then recover (never error).

## After each run

- [ ] Note the worst moment + the fix; re-run the beaten beat
- [ ] Keep both takes; copy to USB + cloud ([[Submission-Checklist]])
- [ ] Everyone signs: "this run is demo-safe" — no unverified number spoken

Related: [[Storyboard]] · [[QandA-Dry-Run]] · [[Idea-and-Deck]] · RUNBOOK
