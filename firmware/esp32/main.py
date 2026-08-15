"""
VITISH edge-node firmware — ESP32 DevKit (MicroPython).

Streams contract-shaped telemetry to the local VITISH MQTT broker:

    bridge/esp32-1/accel   (1 Hz)  accel window + rms + on-device flag
    bridge/esp32-1/status  (30 s)  heartbeat with rssi / heap / uptime / ts

HONESTY (the backend LIVE badge reads these labels):
  * There is NO accelerometer attached.  The accel window is a deterministic
    SELF-TEST / BIST tone (5 Hz sinusoid + xorshift32 PRNG noise) carrying
    ``signal_kind: "self-test-bist"`` — it is NEVER real bridge vibration.
  * The genuinely measured quantities ARE real: WiFi RSSI (dBm), free heap
    (bytes), device uptime (s), and a wall-clock ts (NTP when reachable).
  * The bridge id is ``esp32-1`` — it is never fused into the z24 BHI.

Drop a real sensor in by replacing ``_window()`` (e.g. read an I2C
ADXL345/MPU-6050) and updating SIGNAL_KIND accordingly.

Flashing:  ampy --port COM6 put firmware/esp32/config.py
           ampy --port COM6 put firmware/esp32/main.py
           ampy --port COM6 reset
"""
import gc
import json
import math
import socket
import struct
import sys
import time

import config
import network

# --- deterministic PRNG — byte-for-byte identical to scripts/edge_sim.py --------
_seed = 0xC0FFEE


def _frand():
    global _seed
    _seed ^= (_seed << 13) & 0xFFFFFFFF
    _seed ^= (_seed >> 17) & 0xFFFFFFFF
    _seed ^= (_seed << 5) & 0xFFFFFFFF
    _seed &= 0xFFFFFFFF
    return ((_seed & 0xFFFF) / 32768.0) - 1.0


def _window():
    out = []
    for i in range(config.WINDOW):
        t = i / float(config.FS)
        v = (config.BIST_AMP *
             math.sin(2.0 * math.pi * config.BIST_HZ * t) +
             config.NOISE_AMP * _frand())
        out.append(round(v, 6))
    return out


def _rms(x):
    return math.sqrt(sum(v * v for v in x) / len(x))


# --- minimal MQTT publisher (MQTT 3.1.1, QoS 0, no external deps) ---------------

def _lvar(n):
    out = b""
    while True:
        d = n % 128
        n //= 128
        if n > 0:
            out += bytes([d | 0x80])
        else:
            return out + bytes([d])


class MQTTClient:
    def __init__(self, host, port=1883, cid="esp32-edge"):
        self.host = host
        self.port = port
        self.cid = cid
        self.sock = None

    def _open(self):
        s = socket.socket()
        s.settimeout(6)
        s.connect(socket.getaddrinfo(self.host, self.port)[0][4])
        return s

    def connect(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        s = self._open()
        cid_b = self.cid.encode()
        # fixed header 0x10 + remaining length; CONNECT 10 bytes + len-prefixed cid
        var = (b"\x00\x04MQTT\x04\x02\x00\x3c"
               + struct.pack(">H", len(cid_b)) + cid_b)
        s.send(b"\x10" + _lvar(len(var)) + var)
        ack = s.recv(4)   # CONNACK: 0x20 len 0x02 rc
        if len(ack) < 4 or ack[0] != 0x20:
            raise OSError("mqtt connack failed")
        self.sock = s

    def publish(self, topic, payload):
        if self.sock is None:
            raise OSError("mqtt not connected")
        tb = topic.encode()
        var = struct.pack(">H", len(tb)) + tb + payload
        self.sock.send(b"\x30" + _lvar(len(var)) + var)   # PUBLISH QoS 0

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


# --- helpers ---------------------------------------------------------------------

def _connect_wifi(wlan, retries=4):
    for attempt in range(retries):
        if wlan.isconnected():
            return
        print("wifi: connecting to %s (attempt %d/%d)"
              % (config.WIFI_SSID, attempt + 1, retries))
        wlan.connect(config.WIFI_SSID, config.WIFI_PASS)
        for _ in range(50):          # up to 10 s
            if wlan.isconnected():
                break
            time.sleep_ms(200)
        if wlan.isconnected():
            break
    print("wifi: connected=%s ip=%s" % (wlan.isconnected(), wlan.ifconfig()[0]))


def _rssi(wlan):
    try:
        v = wlan.status("rssi")
        return v if isinstance(v, int) else None
    except Exception:
        return None


def main():
    print("=== vitish-edge-esp32 boot ===")
    print("mpy:", "%d.%d.%d" % (sys.version_info[0], sys.version_info[1],
                                sys.version_info[2]))

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    _connect_wifi(wlan)

    # NTP wall-clock (best effort — time.time() then returns epoch seconds)
    try:
        import ntptime
        ntptime.settime()
        print("ntp: synced ts=%d" % time.time())
    except Exception as exc:
        print("ntp: skipped (%s) — ts is boot-relative" % exc)

    mqtt = MQTTClient(config.MQTT_HOST, config.MQTT_PORT, config.CLIENT_ID)
    _t0 = time.ticks_ms()
    baseline = None
    pub_n = 0
    connected = False

    while True:
        # 1) WiFi watchdog
        if not wlan.isconnected():
            print("wifi: dropped — reconnecting")
            _connect_wifi(wlan)
        # 2) MQTT watchdog
        if not connected:
            try:
                mqtt.connect()
                connected = True
                print("mqtt: connected to %s:%d" % (config.MQTT_HOST,
                                                    config.MQTT_PORT))
            except OSError as exc:
                print("mqtt: connect failed (%s) — retry in 3s" % exc)
                time.sleep(3)
                continue

        # 3) build the honest self-test window
        samples = _window()
        rms = _rms(samples)
        baseline = rms if baseline is None else 0.95 * baseline + 0.05 * rms
        flag = 1 if (rms > config.FLAG_FACTOR * baseline
                     and rms > config.FLAG_FLOOR) else 0
        pub_n += 1
        uptime_s = time.ticks_diff(time.ticks_ms(), _t0) // 1000
        heap = gc.mem_free()
        rssi = _rssi(wlan)

        accel = {
            "bridge": config.BRIDGE, "node": config.NODE, "ts": time.time(),
            "fs": config.FS, "samples": samples, "rms": round(rms, 5),
            "flag": flag, "signal_kind": config.SIGNAL_KIND,
            "source": config.BRIDGE, "rssi": rssi, "heap": heap,
            "uptime_s": uptime_s, "fw": config.FW,
        }
        try:
            mqtt.publish("bridge/%s/accel" % config.BRIDGE,
                         json.dumps(accel).encode())
        except OSError as exc:
            print("mqtt: publish failed (%s) — reconnect" % exc)
            connected = False
            continue

        if pub_n % config.STATUS_EVERY == 0:
            status = {
                "bridge": config.BRIDGE, "node": config.NODE, "ts": time.time(),
                "online": True, "firmware": config.FW, "rssi": rssi,
                "heap": heap, "uptime_s": uptime_s,
                "signal_kind": config.SIGNAL_KIND,
            }
            try:
                mqtt.publish("bridge/%s/status" % config.BRIDGE,
                             json.dumps(status).encode())
            except OSError as exc:
                print("mqtt: status publish failed (%s)" % exc)

        if pub_n % 5 == 0:
            print("accel #%d rms=%.4f flag=%d rssi=%s heap=%d uptime=%ds"
                  % (pub_n, rms, flag, rssi, heap, uptime_s))
        time.sleep_ms(config.PUBLISH_MS)

    # unreachable — the watchdog loop above runs forever


if __name__ == "__main__":
    main()
