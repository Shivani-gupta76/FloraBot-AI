// Copy this file to secrets.h (same folder) and fill in your values. Never commit secrets.h.

#define WIFI_SSID "your-wifi-name"
#define WIFI_PASSWORD "your-wifi-password"

// The FastAPI laptop's LAN address, e.g. "http://192.168.1.50:8000". No trailing slash.
#define SERVER_URL "http://192.168.1.50:8000"

// Must match FLORABOT_DEVICE_ID and FLORABOT_DEVICE_TOKEN in backend/.env.
#define DEVICE_ID "esp32-led1"
#define DEVICE_TOKEN "paste-the-same-token-as-the-backend"
