/*
 * VITISH 2026 · PS#99 SHM — ESP-01S edge node configuration.
 *
 * Everything the node needs to come alive on YOUR network. Fill in the WiFi
 * credentials and the MQTT broker address, then compile + flash.
 */
#ifndef VITISH_ESP01_CONFIG_H
#define VITISH_ESP01_CONFIG_H

// ---- WiFi network the ESP-01S joins (2.4 GHz only — no 5 GHz support) -------
// Use the same network your laptop (running the VITISH backend) is on.
#define WIFI_SSID "YOUR_2_4GHZ_SSID"
#define WIFI_PASS "YOUR_WIFI_PASSWORD"

// ---- MQTT broker = the laptop running the VITISH backend --------------------
// The ESP must reach this IP:port over the LAN. Find the laptop's Wi-Fi IPv4
// with `ipconfig` (the "Wireless LAN adapter Wi-Fi" line, e.g. 172.20.169.83).
// A broker must be listening on 1883 (e.g. `python -m amqtt` or Mosquitto).
#define MQTT_HOST IPAddress(172, 20, 169, 83)
#define MQTT_PORT 1883

// ---- node identity ----------------------------------------------------------
// This ESP-01S fills the "esp01-1" edge slot.  The backend's edge monitor and
// recorder subscribe to EVERY id in VITISH_EDGE_BRIDGES (default "esp32-1,
// esp01-1" — see backend/app/edge_node.py, S8 fix), so a stock-flashed ESP-01S
// publishing bridge/esp01-1/... is NEVER silently ignored.  Keep BRIDGE_ID a
// per-device id ("esp01-1") — do NOT reuse the ESP32's id, or the twin would
// mislabel this board's real hardware.  Run a host simulator for this slot with
// `python scripts/edge_sim.py --bridge esp01-1`.
#define BRIDGE_ID    "esp01-1"
#define NODE_ID      1
#define FW_VERSION   "vitish-edge-esp01-0.1"
#define SIGNAL_KIND  "self-test-bist"   // honest label: no sensor on the ESP-01S
#define SOURCE       "esp01-1"

// ---- streaming --------------------------------------------------------------
#define PUBLISH_MS   1000               // one 1 s window per message
#define NTP_SERVER   "pool.ntp.org"     // used for wall-clock ts when reachable

#endif  // VITISH_ESP01_CONFIG_H
