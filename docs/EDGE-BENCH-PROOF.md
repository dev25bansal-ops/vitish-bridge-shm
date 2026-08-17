# Edge Bench Proof — documented SIM proof (item 11)

**Status:** DONE via the *documented sim proof if no board* branch (2026-08-17).
**Constraint honored:** no board was flashed or bench-tested (Key-Decisions #11;
H8-gated stretch).  The physical board → MQTT leg is the only unproven link;
everything on the backend/API side is proven with real-shaped packets.

---

## 1. The declared bench-proof protocol (what a real proof would do)

1. Flash MicroPython + `firmware/esp32/config.py` + `firmware/esp32/main.py`
   onto an ESP32 DevKit (CP2102) with the Ampy tooling in `tools/esp`
   (`ampy --port COM<X> put …` + `reset`), after filling in the WiFi SSID/pass
   and the laptop's MQTT IP in `config.py`.
2. Power the board; it joins 2.4 GHz WiFi and publishes contract-shaped
   telemetry to the local MQTT broker: `bridge/esp32-1/accel` (1 Hz) and
   `bridge/esp32-1/status` (30 s heartbeat) — the esp01-1 slot is the same with
   a stock-flashed ESP-01S (`firmware/esp01/vitish_edge_esp01.ino`).
3. Start the backend stack (`python app/run_all.py`, local broker up).  The
   banner should flip to `Edge node : bridge=esp32-1,esp01-1 primary=esp32-1
   ONLINE (N rx)`.
4. `GET /api/bridge/esp32-1/state` → `live: true, online: true`,
   `signal_kind: "self-test-bist"`, and the `honesty` block.
5. `GET /api/manifest` → `edge_node.status.online: true`.
6. Watch the twin edge status card (Phase-4 item #39) with the honest BIST
   labels.
7. Confirm the item-15 LIVE-badge gate flips `live` only on real received
   packets.

## 2. What is actually committed and proven

| Piece | Location | Proof status |
|---|---|---|
| ESP32 firmware (MicroPython) | `firmware/esp32/main.py` + `config.py` | **COMMITTED** — deterministic 5 Hz self-test/BIST tone + xorshift32 PRNG, RSSI/heap/uptime/NTP-ts measured, `signal_kind: self-test-bist` |
| ESP-01S firmware (Arduino) | `firmware/esp01/vitish_edge_esp01.ino` + `config.h` | **COMMITTED** — same honest BIST tone, `bridge esp01-1`, no ADC (S8) |
| Flash tooling + MicroPython images + CP210x driver installer | `tools/esp/` | **COMMITTED** — `ampy_put.py`, `esp32-micropython-v1.28.0.bin`, `esp8266-1m-micropython-v1.28.0.bin`, `install_cp210x.ps1` |
| Host-side node simulator | `scripts/edge_sim.py` | **COMMITTED** — byte-for-byte identical signal logic to the firmware; publishes the same messages a real board will send (`--bridge esp01-1` for the ESP-01S slot); explicitly a TEST HARNESS, not a data source |
| Backend edge monitor | `backend/app/edge_node.py` (`EdgeNodeMonitor`) | **PROVEN** — watches every slot in `EDGE_BRIDGES` (`esp32-1, esp01-1`), per-slot state, honest `signal_kind` + `honesty` block; 54-check `backend/tests/test_edge_node.py` PASS |
| Backend per-slot recorders | `backend/app/run_all.py` | **PROVEN** — a recorder subscribes to every edge slot so a stock ESP-01S row is never silently dropped (S8); test asserted |
| REST surface | `backend/app/api.py` `GET /api/bridge/esp32-1/state` + `esp01-1/state` + manifest `edge_node` block | **PROVEN** — via the item-15 honesty-label gate (46 checks) + edge-node API tests |
| LIVE-badge gating | item-15 `backend/tests/test_honesty_gate.py` | **PROVEN** — unwitnessed slot → `live: false` + OFF-LINE label; real-shaped packet → `live: true` but accel still labeled BIST (never real vibration) |

**Exact reproduction of the proven leg (no broker, no board):**

```bash
python backend/tests/test_edge_node.py      # 54 checks: monitor + esp01 slot + recorder + API + manifest
python backend/tests/test_honesty_gate.py   # 46 checks: LIVE-badge gating + every label present
```

With a broker up, the MQTT leg is exercised by the host simulator:

```bash
python scripts/edge_sim.py --broker 127.0.0.1 --port 1883 --bridge esp32-1   # or --bridge esp01-1
```

## 3. Honest statement (rehearse this verbatim)

The backend edge-monitor + recorder + REST/manifest surface is fully wired and
regression-tested with real-shaped packets, and the firmware + flash tooling
are committed and ready.  **No physical board was ever flashed or streamed a
packet** — that is the H8-gated stretch (Key-Decisions #11).  The edge bridge's
`live` flag is gated on a real measured packet (item 15): with no board it reads
`false` with an explicit OFF-LINE label, and even an online node labels its
accel as the self-test BIST tone — never real bridge vibration.  The twin shows
**no LIVE badge** for the edge slot until a board is actually bench-tested.

Related: `docs/COMPREHENSIVE-ANALYSIS.md` §7.6 item 11 + item 15 ·
`vault/05-Demo/QandA-Dry-Run.md` guardrails · `vault/04-Build/Data-Pipeline.md`
("Edge node (stretch)") · Phase-4 task #39 (twin edge status card).