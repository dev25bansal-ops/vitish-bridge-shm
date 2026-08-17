"""
VITISH edge-node config — ESP32 DevKit (MicroPython).

Edit WIFI_SSID / WIFI_PASS before flashing.  MQTT_HOST is the laptop's
WiFi IP (run `ipconfig` — the Wi-Fi adapter IPv4).  The accel stream is a
labeled SELF-TEST/BIST tone (no accelerometer attached); RSSI / free-heap /
uptime / NTP-ts are the real measured quantities.  Keep this file honest:
never claim the tone is bridge vibration.
"""

# --- WiFi --------------------------------------------------------------------
WIFI_SSID = "YOUR_2_4GHZ_SSID"     # <-- fill in
WIFI_PASS = "YOUR_WIFI_PASSWORD"   # <-- fill in

# --- MQTT (local VITISH broker on the laptop) ---------------------------------
MQTT_HOST = "172.20.169.83"        # laptop WiFi IPv4 (ipconfig)
MQTT_PORT = 1883

# --- identity ----------------------------------------------------------------
# This ESP32 fills the "esp32-1" edge slot — the PRIMARY id in the backend's
# EDGE_BRIDGES set (default "esp32-1, esp01-1", see backend/app/edge_node.py).
# The monitor + recorder subscribe to every id in that set, so keep this id
# distinct from the ESP-01S's "esp01-1": each board is labelled by its real
# hardware, never mislabeled.
BRIDGE = "esp32-1"                 # primary edge slot (backend EDGE_BRIDGES[0])
NODE = 1
FW = "vitish-edge-esp32-0.1"
SIGNAL_KIND = "self-test-bist"     # honest label — tone, not real vibration
CLIENT_ID = "vitish-edge-esp32-1"

# --- signal (self-test BIST tone, deterministic xorshift32 noise) -------------
FS = 100            # Hz
WINDOW = 100        # samples per window (1 s)
BIST_HZ = 5.0       # tone frequency
BIST_AMP = 0.05     # tone amplitude (m/s^2)
NOISE_AMP = 0.004   # PRNG noise amplitude
FLAG_FACTOR = 2.5   # edge-anomaly flag threshold (vs rolling baseline)
FLAG_FLOOR = 0.10   # absolute floor so tiny tones never flag
PUBLISH_MS = 1000   # accel cadence (1 Hz)

# --- extras ------------------------------------------------------------------
STATUS_EVERY = 30   # publish /status heartbeat every N accel windows
