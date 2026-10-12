"""
Simulated sensor nodes. Publishes raw readings for 16 houses to MQTT, standing in
for the real ESP32 -> Zigbee -> gateway chain.

Used two ways:
  - inside the web app (DEMO_SIMULATOR=1), controlled from the /demo-control web page
  - (the old terminal simulator.py was removed; the web page replaces it)
"""
import json
import random
import threading
import time
import config
import db
import mqtt_helper

NUM_HOUSES = 16
PUBLISH_INTERVAL_SECONDS = 10

VALID = ("normal", "leak", "no_supply")


def set_scenario(house_id, scenario):
    """Stored in the database so every web worker (and the simulator) sees the same choice."""
    if scenario not in VALID or not (1 <= house_id <= NUM_HOUSES):
        raise ValueError("invalid house or scenario")
    conn = db.get_conn()
    conn.execute("INSERT OR REPLACE INTO demo_scenarios (house_id, scenario) VALUES (?, ?)", (house_id, scenario))
    conn.commit()
    conn.close()


def reset_all():
    conn = db.get_conn()
    conn.execute("DELETE FROM demo_scenarios")
    conn.commit()
    conn.close()


def get_scenarios():
    scenarios = {i: "normal" for i in range(1, NUM_HOUSES + 1)}
    conn = db.get_conn()
    for row in conn.execute("SELECT house_id, scenario FROM demo_scenarios"):
        if row["house_id"] in scenarios and row["scenario"] in VALID:
            scenarios[row["house_id"]] = row["scenario"]
    conn.close()
    return scenarios


def generate_reading(scenario):
    # returns (pressure, flow) using the ranges from rules.py
    if scenario == "leak":          # flow >= 6 and 0 < pressure < 50
        return round(random.uniform(10.0, 45.0), 2), round(random.uniform(6.5, 12.0), 2)
    if scenario == "no_supply":     # flow == 0 and pressure == 0
        return 0.0, 0.0
    return round(random.uniform(80.0, 150.0), 2), round(random.uniform(0.0, 5.0), 2)


def _publisher_loop(client):
    while True:
        scenarios = get_scenarios()
        for house_id in range(1, NUM_HOUSES + 1):
            pressure, flow = generate_reading(scenarios[house_id])
            payload = json.dumps({"house_id": house_id, "pressure": pressure, "flow": flow})
            client.publish(f"{config.MQTT_PREFIX}/house{house_id:02d}/data", payload)
        time.sleep(PUBLISH_INTERVAL_SECONDS)


def start_publisher():
    client = mqtt_helper.make_client()
    mqtt_helper.connect_and_loop(client)
    threading.Thread(target=_publisher_loop, args=(client,), daemon=True).start()
    print("[SIM] Simulator publishing for 16 houses")
    return client
