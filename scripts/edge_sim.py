#!/usr/bin/env python
"""
Host-side simulator for the ESP32 edge node (bridge='esp32-1').

Replicates the firmware's EXACT signal logic (deterministic xorshift PRNG, 5 Hz
self-test/BIST tone, rolling RMS, on-device flag) and publishes contract-shaped
payloads to a local MQTT broker on bridge/esp32-1/accel + /status — the same
messages the real board (firmware/esp32) will send.  Used to bench-test the
backend LIVE-badge path before the ESP is on the network.

Honest by construction: the accel window is the labeled self-test tone, exactly
as the device sends it.  This script is a TEST HARNESS, not a data source.

Usage:
    python scripts/edge_sim.py --broker 127.0.0.1 --port 1883 [--secs 15]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time

import paho.mqtt.client as mqtt

BRIDGE = "esp32-1"
NODE = 1
FW = "vitish-edge-esp32-0.1"
SIGNAL_KIND = "self-test-bist"
FS = 100
WINDOW = 100
BIST_HZ = 5.0
BIST_AMP = 0.05
NOISE_AMP = 0.004
FLAG_FACTOR = 2.5
FLAG_FLOOR = 0.10

# deterministic xorshift32 — identical to the firmware's _frand()
_seed = 0xC0FFEE


def _frand() -> float:
    global _seed
    _seed ^= (_seed << 13) & 0xFFFFFFFF
    _seed ^= (_seed >> 17) & 0xFFFFFFFF
    _seed ^= (_seed << 5) & 0xFFFFFFFF
    _seed &= 0xFFFFFFFF
    return ((_seed & 0xFFFF) / 32768.0) - 1.0


def _window() -> list:
    out = []
    for i in range(WINDOW):
        t = i / float(FS)
        v = BIST_AMP * math.sin(2.0 * math.pi * BIST_HZ * t) + NOISE_AMP * _frand()
        out.append(round(v, 6))
    return out


def _rms(x: list) -> float:
    return math.sqrt(sum(v * v for v in x) / len(x))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--secs", type=int, default=12)
    args = ap.parse_args()

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                         client_id="edge-sim-host")
    client.reconnect_delay_set(min_delay=1, max_delay=5)

    def on_connect(c, u, f, rc, props):
        if getattr(rc, "value", -1) == 0:
            print(f"[sim] connected to {args.broker}:{args.port}")
            # status heartbeat exactly as the firmware sends it
            client.publish(
                f"bridge/{BRIDGE}/status",
                json.dumps({"bridge": BRIDGE, "node": NODE, "ts": time.time(),
                            "online": True, "firmware": FW, "rssi": -60,
                            "signal_kind": SIGNAL_KIND}), qos=0)

    client.on_connect = on_connect
    client.connect(args.broker, args.port, keepalive=30)
    client.loop_start()

    t_end = time.time() + args.secs
    baseline = None
    sent = 0
    while time.time() < t_end:
        samples = _window()
        rms = _rms(samples)
        baseline = rms if baseline is None else 0.95 * baseline + 0.05 * rms
        flag = 1 if (rms > FLAG_FACTOR * baseline and rms > FLAG_FLOOR) else 0
        payload = {
            "bridge": BRIDGE, "node": NODE, "ts": round(time.time(), 3),
            "fs": FS, "samples": samples, "rms": round(rms, 5), "flag": flag,
            "signal_kind": SIGNAL_KIND, "source": BRIDGE, "rssi": -60,
            "heap": 28480, "uptime_s": int(time.time() - 1700000000),
            "fw": FW,
        }
        info = client.publish(f"bridge/{BRIDGE}/accel", json.dumps(payload), qos=0)
        sent += 1
        if sent % 5 == 0:
            print(f"[sim] sent {sent} accel msgs (rms={rms:.4f} flag={flag})")
        time.sleep(1.0)

    client.loop_stop()
    client.disconnect()
    print(f"[sim] done — {sent} messages published to bridge/{BRIDGE}/accel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
