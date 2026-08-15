/*
 * VITISH 2026 · PS#99 SHM — ESP-01S edge node firmware.
 *
 * The real-hardware arm of the "LIVE" badge on the digital twin. It publishes
 * contract-shaped telemetry to the VITISH MQTT broker on bridge/esp01-1/accel
 * so the existing backend subscriber (bridge/+/#) routes it straight into the
 * pipeline — no new server-side ingestion needed.
 *
 * HONESTY (read before claiming anything in the demo):
 *  - The ESP-01S has NO accelerometer (only GPIO0/GPIO2 are broken out; no ADC).
 *    The 100-sample accel window is a deterministic SELF-TEST / BIST calibration
 *    tone (5 Hz, 0.05 m/s^2) that exercises the exact contract shape + on-device
 *    rolling-RMS flag logic a real sensor channel would. The payload carries
 *    `signal_kind: "self-test-bist"` and any UI MUST label it as such — this is
 *    never presented as real bridge vibration.
 *  - Real measured quantities ARE streamed: WiFi RSSI (dBm), free heap (bytes),
 *    uptime (s), plus a wall-clock ts via NTP when the network reaches it.
 *  - The demo arc (z24 BHI) is untouched: this is a separate bridge id, never
 *    fused into the hero bridge's BHI.
 *
 * Build/flash (arduino-cli):
 *   arduino-cli compile --fqbn esp8266:esp8266:generic:xtal=80,vt=flash,eesz=1M64 \
 *       --build-property build.extra_flags=-DMQTT_MAX_PACKET_SIZE=2048 firmware/esp01
 *   arduino-cli upload -p COM5 --fqbn esp8266:esp8266:generic:xtal=80,vt=flash,eesz=1M64 firmware/esp01
 */
#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <time.h>
#include "config.h"

// ---- self-test (BIST) tone --------------------------------------------------
static const int    FS        = 100;      // Hz (matches the VITISH contract)
static const int    WINDOW    = 100;      // one 1 s window of samples
static const float  BIST_HZ   = 5.0f;     // calibration tone frequency
static const float  BIST_AMP  = 0.05f;    // m/s^2 tone amplitude (self-test only)
static const float  NOISE_AMP = 0.004f;   // tiny deterministic dither
static const float  FLAG_FACTOR = 2.5f;   // flag when rms > factor * baseline
static const float  FLAG_FLOOR   = 0.10f; // absolute floor for the flag test

WiFiClient     _wifi;
PubSubClient   _mqtt(_wifi);
unsigned long  _lastPub = 0;
unsigned long  _bootMs  = millis();
bool           _haveNtp = false;

// deterministic PRNG so the self-test signal is reproducible across reboots
static uint32_t _seed = 0xC0FFEEu;
static float _frand() {
  _seed ^= _seed << 13;
  _seed ^= _seed >> 17;
  _seed ^= _seed << 5;
  return ((_seed & 0xFFFFu) / 32768.0f) - 1.0f;  // ~[-1, 1]
}

static void _print_state(const char *tag) {
  Serial.printf("[%s] rssi=%d dBm heap=%u uptime=%lu s\n",
                tag, (int)WiFi.RSSI(), (unsigned)ESP.getFreeHeap(),
                (unsigned long)(millis() / 1000));
}

static void _ensure_ntp() {
  if (_haveNtp) return;
  configTime(0, 0, NTP_SERVER);   // UTC; twin knows the bridge timezone
  _haveNtp = time(nullptr) > 1500000000UL;   // a sane epoch => sync succeeded
}

static void _connect_wifi() {
  Serial.printf("[wifi] connecting to %s ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);            // low-latency for telemetry cadence
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    delay(250);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[wifi] connected, ip=%s\n", WiFi.localIP().toString().c_str());
    _ensure_ntp();
  } else {
    Serial.println("[wifi] FAILED to connect (retrying in loop)");
  }
}

static void _connect_mqtt() {
  if (_mqtt.connected()) return;
  if (_mqtt.connect(BRIDGE_ID)) {
    Serial.print("[mqtt] connected to ");
    Serial.print(MQTT_HOST);
    Serial.print(":");
    Serial.println(MQTT_PORT);
    // status heartbeat per the contract (bridge/{id}/status)
    char st[256];
    snprintf(st, sizeof(st),
             "{\"bridge\":\"%s\",\"node\":%d,\"ts\":%lu,\"online\":true,"
             "\"firmware\":\"%s\",\"rssi\":%d,\"signal_kind\":\"%s\"}",
             BRIDGE_ID, NODE_ID, (unsigned long)_now_s(), FW_VERSION,
             (int)WiFi.RSSI(), SIGNAL_KIND);
    _mqtt.publish("bridge/" BRIDGE_ID "/status", st);
    _print_state("mqtt");
  } else {
    Serial.printf("[mqtt] connect failed rc=%d\n", _mqtt.state());
  }
}

// wall-clock when NTP sync worked, else seconds since boot (honest fallback)
static unsigned long _now_s() {
  if (_haveNtp) {
    time_t t = time(nullptr);
    if (t > 1500000000UL) return (unsigned long)t;
  }
  return (unsigned long)(millis() / 1000);
}

static void _publish_accel() {
  float samples[WINDOW];
  float sum_sq = 0.0f;
  for (int i = 0; i < WINDOW; i++) {
    float t  = i / (float)FS;
    float v  = BIST_AMP * sinf(2.0f * PI * BIST_HZ * t) + NOISE_AMP * _frand();
    samples[i] = v;
    sum_sq += v * v;
  }
  float rms  = sqrtf(sum_sq / WINDOW);
  // rolling baseline (self-test is near-constant; baseline ~ rms of first window)
  static float baseline = -1.0f;
  if (baseline < 0.0f) baseline = rms;
  baseline = 0.95f * baseline + 0.05f * rms;
  int flag = (rms > FLAG_FACTOR * baseline && rms > FLAG_FLOOR) ? 1 : 0;

  char buf[1800];
  int n = snprintf(buf, sizeof(buf),
                   "{\"bridge\":\"%s\",\"node\":%d,\"ts\":%lu,\"fs\":%d,\"samples\":[",
                   BRIDGE_ID, NODE_ID, _now_s(), FS);
  for (int i = 0; i < WINDOW && n < (int)sizeof(buf) - 64; i++) {
    n += snprintf(buf + n, sizeof(buf) - n, "%.4f%s", samples[i],
                  (i < WINDOW - 1) ? "," : "");
  }
  snprintf(buf + n, sizeof(buf) - n,
           "],\"rms\":%.5f,\"flag\":%d,\"signal_kind\":\"%s\",\"source\":\"%s\","
           "\"rssi\":%d,\"heap\":%u,\"uptime_s\":%lu,\"fw\":\"%s\"}",
           rms, flag, SIGNAL_KIND, SOURCE, (int)WiFi.RSSI(),
           (unsigned)ESP.getFreeHeap(), _now_s(), FW_VERSION);

  bool ok = _mqtt.publish("bridge/" BRIDGE_ID "/accel", buf);
  Serial.printf("[accel] pub=%s rms=%.4f flag=%d len=%d\n",
                ok ? "ok" : "FAIL", rms, flag, n);
}

void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println("VITISH edge node (ESP-01S) booting ...");
  _connect_wifi();
  _mqtt.setServer(MQTT_HOST, MQTT_PORT);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    _connect_wifi();
    delay(1000);
  }
  if (WiFi.status() == WL_CONNECTED && !_mqtt.connected()) {
    _connect_mqtt();
    delay(500);
  }
  _mqtt.loop();                     // keepalive / PINGREQ processing
  unsigned long nowMs = millis();
  if (WiFi.status() == WL_CONNECTED && _mqtt.connected() &&
      nowMs - _lastPub >= PUBLISH_MS) {
    _lastPub = nowMs;
    _publish_accel();
  }
}
