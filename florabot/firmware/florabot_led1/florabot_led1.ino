// FloraBOT AI - LED1 watering alert.
// Polls the FastAPI backend for LED1 commands, applies them and sends an acknowledgement.
// Needs the ArduinoJson library (version 7) from the Arduino Library Manager.

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

#include "secrets.h"

// GPIO 2 drives the on-board LED on many ESP32 DevKit boards. Change it to match your wiring.
const int LED1_PIN = 2;
const unsigned long POLL_INTERVAL_MS = 3000;

bool led1On = false;

void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  Serial.printf("Connecting to Wi-Fi %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nConnected, IP address %s\n", WiFi.localIP().toString().c_str());
}

int post(const String& path, const String& body, String& response) {
  HTTPClient http;
  http.begin(String(SERVER_URL) + path);
  http.setTimeout(5000);
  http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
  http.addHeader("Content-Type", "application/json");
  int status = http.POST(body);
  response = status > 0 ? http.getString() : "";
  http.end();
  return status;
}

void acknowledge(const char* commandId, bool success) {
  JsonDocument ack;
  ack["device_id"] = DEVICE_ID;
  ack["success"] = success;
  ack["led_state"] = led1On ? "ON" : "OFF";
  String body;
  serializeJson(ack, body);

  String response;
  int status = post(String("/api/device/commands/") + commandId + "/ack", body, response);
  Serial.printf("Ack %s -> HTTP %d %s\n", commandId, status, response.c_str());
}

void pollOnce() {
  String response;
  int status = post("/api/device/poll", "{}", response);
  if (status != 200) {
    Serial.printf("Poll failed: HTTP %d\n", status);
    return;
  }

  JsonDocument doc;
  if (deserializeJson(doc, response)) {
    Serial.println("Poll response was not valid JSON");
    return;
  }
  JsonVariant command = doc["command"];
  if (command.isNull()) {
    return;
  }

  const char* commandId = command["command_id"] | "";
  const char* led = command["led"] | "";
  const char* state = command["requested_state"] | "";
  const char* deviceId = command["device_id"] | "";
  Serial.printf("Command %s: %s %s\n", commandId, led, state);

  bool valid = strcmp(led, "LED1") == 0 && strcmp(deviceId, DEVICE_ID) == 0 &&
               (strcmp(state, "ON") == 0 || strcmp(state, "OFF") == 0);
  if (valid) {
    // Setting a state (not toggling) makes a re-delivered command harmless.
    led1On = strcmp(state, "ON") == 0;
    digitalWrite(LED1_PIN, led1On ? HIGH : LOW);
  }
  acknowledge(commandId, valid);
}

void setup() {
  Serial.begin(115200);
  pinMode(LED1_PIN, OUTPUT);
  digitalWrite(LED1_PIN, LOW);
  connectWifi();
}

void loop() {
  connectWifi();
  pollOnce();
  delay(POLL_INTERVAL_MS);
}
