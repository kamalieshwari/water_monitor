"""
Central settings. Every value comes from an environment variable (set in
render.yaml on Render, or in your terminal locally), with a safe default.
"""
import os


def _flag(name, default="0"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "water_monitor.db"))

MQTT_HOST = os.environ.get("MQTT_HOST", "broker.hivemq.com")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TLS = _flag("MQTT_TLS", "0")
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")
MQTT_PREFIX = os.environ.get("MQTT_PREFIX", "wm-CHANGE-THIS-7421")

MUNICIPALITY_PASSWORD = os.environ.get("MUNICIPALITY_PASSWORD", "admin123")

DEMO_MODE = _flag("DEMO_MODE", "1")            # 1 = thresholds in minutes, 0 = days
DEMO_SIMULATOR = _flag("DEMO_SIMULATOR", "1")  # 1 = app runs the fake sensors itself

# ---- SMS / OTP ----
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "console").strip().lower()   # console | twilio | msg91
COUNTRY_CODE = os.environ.get("COUNTRY_CODE", "91")                        # used when a 10-digit number is typed
MUNICIPALITY_PHONE = os.environ.get("MUNICIPALITY_PHONE", "")              # receives the 6-day alert
OWNER_PHONES = os.environ.get("OWNER_PHONES", "")                          # "1:9876543210,2:9123456780"
PRESSURE_UNIT = os.environ.get("PRESSURE_UNIT", "psi")                     # shown on the dashboard

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.environ.get("TWILIO_FROM", "")
TWILIO_MESSAGING_SERVICE_SID = os.environ.get("TWILIO_MESSAGING_SERVICE_SID", "")

MSG91_AUTHKEY = os.environ.get("MSG91_AUTHKEY", "")
MSG91_SENDER_ID = os.environ.get("MSG91_SENDER_ID", "")
MSG91_OTP_TEMPLATE_ID = os.environ.get("MSG91_OTP_TEMPLATE_ID", "")      # template vars: ##VAR1## = OTP, ##VAR2## = node id
MSG91_ALERT_TEMPLATE_ID = os.environ.get("MSG91_ALERT_TEMPLATE_ID", "")  # template var:  ##VAR1## = message text
