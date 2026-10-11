"""Small helpers so sim_engine.py and app.py create MQTT clients the same way."""
import paho.mqtt.client as mqtt
import config


def make_client():
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)   # paho-mqtt 2.x
    except AttributeError:
        client = mqtt.Client()                                   # paho-mqtt 1.x
    if config.MQTT_USER:
        client.username_pw_set(config.MQTT_USER, config.MQTT_PASS)
    if config.MQTT_TLS:
        client.tls_set()
    return client


def connect_and_loop(client):
    """Connect in the background and keep retrying, so the app never crashes
    just because the broker is briefly unreachable."""
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=60)
    client.loop_start()
