"""
Main web application. This is the file that ties everything together:

  MQTT readings -> classify -> SQLite -> dashboards (owner + municipality)

Background threads started here (once, when the app loads):
  1. MQTT subscriber   - receives readings, saves them, decides house status
  2. escalation loop   - sends user / municipality notifications on timers
  3. simulator         - fake sensors, only when DEMO_SIMULATOR=1
"""
import encodings.idna  # noqa: F401  preload the hostname codec before any thread starts (fixes 'unknown encoding: idna')
import functools
import hmac
import json
import os
import sys
import threading
import time
import traceback

from flask import Flask, jsonify, redirect, render_template, request, session, url_for, abort
from werkzeug.security import check_password_hash

try:
    sys.stdout.reconfigure(line_buffering=True)   # print() lines reach Render's log at once, not minutes later
except Exception:
    pass

import config
import db
import escalation
import manage_owners
import mqtt_helper
import otp
import seed_data
import sim_engine
from rules import classify, clean_reading

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

CONFIRM_READINGS = 2     # same classification this many times in a row before status changes
PRUNE_EVERY = 1000       # delete old readings after this many messages


# ======================= 1. classify + MQTT subscriber =======================

_pending = {}        # house_id -> (last classification, how many times in a row)
_message_count = 0


def on_message(client, userdata, msg):
    global _message_count
    try:
        data = json.loads(msg.payload.decode())
        house_id = int(data["house_id"])
        pressure = float(data["pressure"])
        flow = float(data["flow"])
    except (ValueError, KeyError, TypeError):
        return                                   # ignore malformed messages
    if not 1 <= house_id <= sim_engine.NUM_HOUSES:
        return

    pressure, flow = clean_reading(pressure, flow)   # same limits/dead-band as the ESP32 rules
    db.save_reading(house_id, pressure, flow)

    status = classify(pressure, flow)
    last, count = _pending.get(house_id, (None, 0))
    count = count + 1 if last == status else 1
    _pending[house_id] = (status, count)
    if count >= CONFIRM_READINGS:                # debounce single noisy readings
        db.update_status(house_id, status)

    _message_count += 1
    if _message_count % PRUNE_EVERY == 0:
        db.prune_readings(hours=24)


def start_subscriber():
    client = mqtt_helper.make_client()
    topic = f"{config.MQTT_PREFIX}/+/data"

    def on_connect(client, userdata, flags, rc, props=None):
        print(f"[MQTT] connected ({rc}); subscribing to {topic}")
        client.subscribe(topic)                  # re-subscribes after every reconnect

    client.on_connect = on_connect
    client.on_message = on_message
    mqtt_helper.connect_and_loop(client)
    return client


# ============================ 2. login + pages ============================

def require_login(role=None):
    def decorator(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            is_api = request.path.startswith("/api/")
            if "house_id" not in session:
                return (jsonify(error="login required"), 401) if is_api else redirect(url_for("login"))
            if role and session.get("role") != role:
                return (jsonify(error="forbidden"), 403) if is_api else redirect(url_for("home"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.after_request
def no_cache(resp):
    """Live data must never be served from a browser or proxy cache."""
    if request.path.startswith("/api/") or request.path in ("/municipality", "/dashboard", "/demo-control"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/debug/threads")
def debug_threads():
    """Shows what every thread is doing right now. Only works when the DEBUG_TOKEN setting is defined."""
    token = os.environ.get("DEBUG_TOKEN", "")
    if not token or not hmac.compare_digest(request.args.get("token", "").encode(), token.encode()):
        abort(404)
    names = {t.ident: t.name for t in threading.enumerate()}
    parts = [f"pid={os.getpid()}  db={config.DB_PATH}  exists={os.path.exists(config.DB_PATH)}  threads={len(names)}"]
    for ident, frame in sys._current_frames().items():
        parts.append(f"--- thread {names.get(ident, ident)}\n" + "".join(traceback.format_stack(frame)))
    return app.response_class("\n".join(parts), mimetype="text/plain")


@app.route("/version")
def version():
    """Which code is running? Nothing secret here; handy to confirm a deploy picked up the latest files."""
    mode = "direct" if _direct_sim() else ("broker" if config.DEMO_SIMULATOR else "hardware")
    return jsonify(build=BUILD, sim_mode=mode, this_worker_runs_services=_is_leader, pid=os.getpid(),
                   uptime=int(time.time() - _BOOT_TIME))


@app.route("/health")
def health():
    return "ok"


@app.route("/")
def home():
    if "house_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("municipality" if session.get("role") == "municipality" else "dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """House owners: mobile number -> OTP by SMS -> logged in."""
    error = info = None
    if request.method == "GET" and request.args.get("reset"):
        session.pop("otp_phone", None)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "request":
            phone = otp.request_otp(request.form.get("phone", ""))
            if phone is None:
                error = "Enter a valid mobile number."
            else:
                session["otp_phone"] = phone
                info = "If this number is registered, an OTP has been sent by SMS."
        elif action == "verify":
            phone = session.get("otp_phone")
            house = otp.verify_otp(phone, request.form.get("otp", "")) if phone else None
            if house:
                session.clear()
                session["house_id"] = house["house_id"]
                session["role"] = house["role"]
                session["name"] = house["owner_name"]
                return redirect(url_for("home"))
            error = "Wrong or expired OTP. Go back to request a new one."

    phone = session.get("otp_phone")
    masked = (phone[:3] + "\u2022" * 6 + phone[-4:]) if phone else ""
    return render_template("login.html", step="verify" if phone else "request",
                           masked=masked, error=error, info=info)


def _owner_password(house_id):
    """Per-house password from the OWNER_PASSWORDS env var, e.g.  3:alpha3,5:beta5  (house:password)."""
    for part in os.environ.get("OWNER_PASSWORDS", "").split(","):
        node, sep, pw = part.strip().partition(":")
        if sep and node.strip().isdigit() and int(node) == house_id and pw:
            return pw
    return ""


@app.route("/staff-login", methods=["GET", "POST"])
def staff_login():
    """Username + password sign-in for the municipality and (optionally) for house owners."""
    error = None
    who = request.values.get("who", "")
    who = who if who in ("municipality", "owner") else ""
    if request.method == "POST":
        t0 = time.time()
        print(f"[LOGIN] attempt for '{request.form.get('username', '').strip()}' ({who or 'any'})")
        user = db.get_user(request.form.get("username", "").strip())
        password = request.form.get("password", "")
        ok = False
        if user and user["role"] == "municipality":
            ok = check_password_hash(user["password_hash"], password)
        elif user and user["role"] == "owner":
            expected = _owner_password(user["house_id"])      # from OWNER_PASSWORDS; empty = password login off for this house
            ok = bool(expected) and hmac.compare_digest(password.encode(), expected.encode())
        print(f"[LOGIN] {'ok' if ok else 'rejected'} after {(time.time() - t0) * 1000:.0f} ms")
        if ok:
            session.clear()
            session["house_id"] = user["house_id"]
            session["role"] = user["role"]
            session["name"] = user["owner_name"]
            return redirect(url_for("home"))
        error = "Wrong username or password."
    return render_template("staff_login.html", error=error, demo=config.DEMO_MODE, who=who)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@require_login("owner")
def dashboard():
    return render_template("dashboard.html", name=session["name"])


@app.route("/municipality")
@require_login("municipality")
def municipality():
    return render_template("municipality.html", name=session["name"],
                           demo=config.DEMO_SIMULATOR, unit=escalation.UNIT)


# ============================ 3. JSON APIs ============================

def house_payload(row):
    status = row["current_status"]
    elapsed = escalation.elapsed_since(row["issue_start_time"]) if status != "normal" else 0
    return {
        "house_id": row["house_id"],
        "owner_name": row["owner_name"],
        "address": row["address"],
        "status": status,
        "elapsed": round(elapsed, 1),
        "unit": escalation.UNIT,
        "node_online": bool(row["node_online"]),
        "last_seen": row["last_seen"],
        "pressure": row["pressure"],
        "flow": row["flow"],
        "pressure_unit": config.PRESSURE_UNIT,
        "flow_unit": "L/min",
        "user_notified": bool(row["user_notified"]),
        "municipality_notified": bool(row["municipality_notified"]),
    }


@app.route("/api/me/status")
@require_login("owner")
def api_me_status():
    house_id = session["house_id"]            # owners can only ever see their own house
    rows = db.get_overview(house_id)
    if not rows:
        return jsonify(error="house not found"), 404
    return jsonify(
        house=house_payload(rows[0]),
        history=db.get_recent_readings(house_id, 30),
        notifications=db.get_notifications(house_id=house_id, kind="user", limit=10),
    )


@app.route("/api/municipality/houses")
@require_login("municipality")
def api_municipality_houses():
    return jsonify(
        houses=[house_payload(r) for r in db.get_overview()],
        alerts=db.get_notifications(kind="municipality", limit=20),
    )


# ============================ 4. demo control ============================

@app.route("/demo-control")
@require_login("municipality")
def demo_control():
    if not config.DEMO_SIMULATOR:
        abort(404)
    return render_template("demo.html")


@app.route("/api/demo/state")
@require_login("municipality")
def api_demo_state():
    if not config.DEMO_SIMULATOR:
        abort(404)
    return jsonify(sim_engine.get_scenarios())


@app.route("/api/demo/set", methods=["POST"])
@require_login("municipality")
def api_demo_set():
    if not config.DEMO_SIMULATOR:
        abort(404)
    data = request.get_json(silent=True) or {}
    try:
        sim_engine.set_scenario(int(data.get("house_id")), data.get("scenario"))
    except (TypeError, ValueError):
        return jsonify(error="invalid house or scenario"), 400
    if _direct_sim():                             # push confirming readings now so dashboards change within seconds
        try:
            _feed_house(int(data.get("house_id")), CONFIRM_READINGS)
        except Exception as e:
            print(f"[SIM] instant update failed: {e}")
    return jsonify(ok=True)


@app.route("/api/demo/reset", methods=["POST"])
@require_login("municipality")
def api_demo_reset():
    if not config.DEMO_SIMULATOR:
        abort(404)
    sim_engine.reset_all()
    if _direct_sim():
        try:
            for house_id in range(1, sim_engine.NUM_HOUSES + 1):
                _feed_house(house_id, CONFIRM_READINGS)
        except Exception as e:
            print(f"[SIM] instant reset failed: {e}")
    return jsonify(ok=True)


# ============================ 5. start everything ============================

class _LocalMsg:
    def __init__(self, payload):
        self.payload = payload


_feed_lock = threading.Lock()


def _direct_sim():
    """True = demo sensors feed the app directly (no MQTT broker). Set DEMO_VIA_BROKER=1 to use the broker."""
    return bool(config.DEMO_SIMULATOR) and os.environ.get("DEMO_VIA_BROKER", "0") != "1"


def _feed_house(house_id, times=1):
    """Make one simulated reading per call for a house and process it exactly like an MQTT message."""
    with _feed_lock:
        for _ in range(times):
            scenario = sim_engine.get_scenarios()[house_id]
            pressure, flow = sim_engine.generate_reading(scenario)
            payload = json.dumps({"house_id": house_id, "pressure": pressure, "flow": flow})
            on_message(None, None, _LocalMsg(payload.encode()))


def _local_simulator():
    """Background loop: fake readings for all 16 houses every few seconds."""
    while True:
        try:
            for house_id in range(1, sim_engine.NUM_HOUSES + 1):
                _feed_house(house_id)
        except Exception as e:                    # never let the demo thread die
            print(f"[SIM] error: {e}")
        time.sleep(sim_engine.PUBLISH_INTERVAL_SECONDS)


BUILD = "2026-10-12-d"
_BOOT_TIME = time.time()
_started = False
_is_leader = False
_leader_lock_file = None


def _become_leader():
    """If gunicorn runs several workers, only one may run the simulator, escalation and MQTT threads.
    The first worker to take this lock file is the leader; the others only serve web pages."""
    global _leader_lock_file
    try:
        import fcntl
    except ImportError:                           # e.g. Windows: always a single process
        return True
    import hashlib
    import tempfile
    name = "water_monitor_" + hashlib.md5(config.DB_PATH.encode()).hexdigest()[:8] + ".lock"
    try:
        _leader_lock_file = open(os.path.join(tempfile.gettempdir(), name), "w")
        fcntl.flock(_leader_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def startup():
    global _started, _is_leader
    if _started:
        return
    _started = True
    print(f"[BOOT] pid={os.getpid()} python={sys.version.split()[0]} db={config.DB_PATH}")
    seed_data.seed()                                                    # tables + demo accounts
    manage_owners.apply_env_phones()                                    # real mobile numbers from OWNER_PHONES
    if not _become_leader():
        print("[BOOT] another worker runs the background services; this worker only serves web pages")
        return
    _is_leader = True
    print("[BOOT] this worker runs the background services (simulator, escalation, MQTT)")
    threading.Thread(target=escalation.start_escalation_loop, daemon=True).start()
    if _direct_sim():
        # Demo mode: the fake sensors hand readings straight to the app (no MQTT broker needed).
        threading.Thread(target=_local_simulator, daemon=True).start()
        print("[SIM] Built-in simulator running (direct mode, no broker)")
        return
    start_subscriber()
    if config.DEMO_SIMULATOR:
        sim_engine.start_publisher()          # DEMO_VIA_BROKER=1: send through the MQTT broker instead


startup()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
