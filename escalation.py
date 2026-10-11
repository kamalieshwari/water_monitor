"""
Runs on a timer (started as a background thread from app.py). Tracks how
long each house has been in a non-normal state and fires notifications at
the configured thresholds.

Thresholds (per latest spec):
  - possible_leak sustained 3 days -> notify user
  - no_supply     sustained 4 days -> notify user
  - no_supply     sustained 6 days -> notify municipality
    (possible_leak NEVER escalates to municipality on its own)

DEMO_MODE: set True to use MINUTES instead of days, so you can show the
full escalation sequence in a few minutes during a live demo, without
waiting real days. Flip to False for the "real" deployed thresholds.
"""

import time
import datetime
import db
import config
import sms

DEMO_MODE = config.DEMO_MODE

if DEMO_MODE:
    LEAK_USER_THRESHOLD = 3      # minutes, stands in for "3 days"
    NO_SUPPLY_USER_THRESHOLD = 4     # minutes, stands in for "4 days"
    NO_SUPPLY_MUNICIPALITY_THRESHOLD = 6   # minutes, stands in for "6 days"
    UNIT = "minutes"
else:
    LEAK_USER_THRESHOLD = 3
    NO_SUPPLY_USER_THRESHOLD = 4
    NO_SUPPLY_MUNICIPALITY_THRESHOLD = 6
    UNIT = "days"

CHECK_INTERVAL_SECONDS = 15  # how often this job runs
NODE_OFFLINE_MINUTES = 20


def elapsed_since(timestamp_str):
    """Returns elapsed time in the same unit as the thresholds (minutes or days)."""
    if not timestamp_str:
        return 0
    started = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    delta = datetime.datetime.utcnow() - started
    if UNIT == "minutes":
        return delta.total_seconds() / 60.0
    return delta.days


def notify_user(house, status, elapsed):
    text = (
        f"Possible leak detected at your property for {elapsed:.0f} {UNIT}. Please inspect your plumbing."
        if status == "possible_leak"
        else f"No water supply detected at your property for {elapsed:.0f} {UNIT}. Please check your connection."
    )
    print(f"[USER NOTIFY] house_id={house['house_id']} phone={house['phone_number']} -> {text}")
    db.log_notification(house["house_id"], "user", text)
    db.mark_notified(house["house_id"], "user_notified")
    sms.send_alert(house["phone_number"], text)


def notify_municipality(house, elapsed):
    text = (
        f"House {house['house_id']} ({house['address']}) has had NO WATER SUPPLY "
        f"for {elapsed:.0f} {UNIT}. Please investigate."
    )
    print(f"[MUNICIPALITY NOTIFY] {text}")
    db.log_notification(house["house_id"], "municipality", text)
    db.mark_notified(house["house_id"], "municipality_notified")
    sms.send_alert(config.MUNICIPALITY_PHONE, text)


def check_node_offline(house):
    if not house["last_seen"]:
        return
    last_seen = datetime.datetime.strptime(house["last_seen"], "%Y-%m-%d %H:%M:%S")
    minutes_since = (datetime.datetime.utcnow() - last_seen).total_seconds() / 60
    if minutes_since > NODE_OFFLINE_MINUTES and house["node_online"]:
        conn = db.get_conn()
        conn.execute("UPDATE house_status SET node_online = 0 WHERE house_id = ?", (house["house_id"],))
        conn.commit()
        conn.close()
        print(f"[NODE OFFLINE] house_id={house['house_id']}")


def evaluate(house):
    status = house["current_status"]

    if status == "normal":
        return  # db.update_status already clears tracking when status returns to normal

    elapsed = elapsed_since(house["issue_start_time"])

    if status == "possible_leak":
        if elapsed >= LEAK_USER_THRESHOLD and not house["user_notified"]:
            notify_user(house, status, elapsed)

    elif status == "no_supply":
        if elapsed >= NO_SUPPLY_MUNICIPALITY_THRESHOLD and not house["municipality_notified"]:
            notify_municipality(house, elapsed)
        elif elapsed >= NO_SUPPLY_USER_THRESHOLD and not house["user_notified"]:
            notify_user(house, status, elapsed)


def run_once():
    for house in db.get_all_statuses_for_escalation():
        if house["house_id"] == 100:   # skip the municipality's own login row
            continue
        check_node_offline(house)
        evaluate(house)


def start_escalation_loop():
    print(f"[ESCALATION] Running every {CHECK_INTERVAL_SECONDS}s, thresholds in {UNIT} "
          f"(leak->user={LEAK_USER_THRESHOLD}, no_supply->user={NO_SUPPLY_USER_THRESHOLD}, "
          f"no_supply->municipality={NO_SUPPLY_MUNICIPALITY_THRESHOLD})")
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"[ESCALATION] error: {e}")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    start_escalation_loop()
