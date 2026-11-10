/*
  ESP32 sensor node for the Smart Poultry House Controller
  Sensors : DHT22 (GPIO 4), MQ-135 (GPIO 34), LDR (GPIO 35),
            HC-SR04 ultrasonic (TRIG 5, ECHO 18)
  Relays  : fan 25, heater 26, feeder 27, lights 14 (4-channel relay module)
  Libraries: DHT sensor library (Adafruit), ArduinoJson
*/
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "DHT.h"

const char* WIFI_SSID = "YOUR_WIFI";
const char* WIFI_PASS = "YOUR_PASSWORD";
// IP address of the laptop running app.py (check with ipconfig)
const char* SERVER = "http://192.168.1.100:5000/api/sensor";
const char* API_KEY = "esp32-poultry-key";

#define DHTPIN 4
#define MQ135_PIN 34
#define LDR_PIN 35
#define TRIG 5
#define ECHO 18
#define FAN 25
#define HEATER 26
#define FEEDER 27
#define LIGHTS 14
#define SILO_DEPTH_CM 50.0   // empty-silo distance from sensor

DHT dht(DHTPIN, DHT22);

float readAmmoniaPPM() {
  // simple linear approximation; calibrate MQ-135 in clean air for accuracy
  int raw = analogRead(MQ135_PIN);
  return raw * (100.0 / 4095.0);
}

float readLux() {
  int raw = analogRead(LDR_PIN);
  return raw * (500.0 / 4095.0);
}

float readFeedLevel() {
  digitalWrite(TRIG, LOW); delayMicroseconds(2);
  digitalWrite(TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  float cm = pulseIn(ECHO, HIGH, 30000) * 0.0343 / 2.0;
  float level = (1.0 - cm / SILO_DEPTH_CM) * 100.0;
  return constrain(level, 0, 100);
}

void setRelay(int pin, bool on) { digitalWrite(pin, on ? LOW : HIGH); } // active-low module

void setup() {
  Serial.begin(115200);
  dht.begin();
  pinMode(TRIG, OUTPUT); pinMode(ECHO, INPUT);
  int relays[] = {FAN, HEATER, FEEDER, LIGHTS};
  for (int p : relays) { pinMode(p, OUTPUT); setRelay(p, false); }
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi connected");
}

void loop() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (isnan(t) || isnan(h)) { Serial.println("DHT22 read failed"); delay(2000); return; }

  StaticJsonDocument<256> doc;
  doc["temperature"] = t;
  doc["humidity"] = h;
  doc["ammonia"] = readAmmoniaPPM();
  doc["light"] = readLux();
  doc["feed_level"] = readFeedLevel();
  String body; serializeJson(doc, body);

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(SERVER);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-API-KEY", API_KEY);
    int code = http.POST(body);
    if (code == 200) {
      StaticJsonDocument<512> res;
      deserializeJson(res, http.getString());
      setRelay(FAN, res["fan"]);
      setRelay(HEATER, res["heater"]);
      setRelay(FEEDER, res["feeder"]);
      setRelay(LIGHTS, res["lights"]);
      Serial.printf("DNN: %s  fan=%d heater=%d\n",
                    (const char*)res["prediction"], (int)res["fan"], (int)res["heater"]);
    } else {
      Serial.printf("Server error %d\n", code);
    }
    http.end();
  }
  delay(3000);
}
