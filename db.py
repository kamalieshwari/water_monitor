"""All database access lives here. Other files never write SQL directly."""
import datetime
import os
import sqlite3

import config

SCHEMA_PATH = os.path.join(config.BASE_DIR, "schema.sql")
TS_FORMAT = "%Y-%m-%d %H:%M:%S"   # same format escalation.py parses (UTC)


def get_conn():
    conn = sqlite3.connect(config.DB_PATH, timeout=30)   # wait up to 30 s if another thread is writing
    conn.row_factory = sqlite3.Row
    try:
        # No disk sync on every commit: writes finish in microseconds, so readers are never kept waiting.
        # (Safe here: demo data on a disk that Render wipes on restart anyway.)
        conn.execute("PRAGMA synchronous=OFF")
    except sqlite3.OperationalError:
        pass
    return conn


def init_db():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        script = f.read()
    conn = get_conn()
    conn.executescript(script)
    conn.commit()
    conn.close()


def _now():
    return datetime.datetime.utcnow().strftime(TS_FORMAT)


# ---------- writes ----------

def save_reading(house_id, pressure, flow):
    now = _now()
    conn = get_conn()
    conn.execute(
        "INSERT INTO readings (house_id, pressure, flow, recorded_at) VALUES (?, ?, ?, ?)",
        (house_id, pressure, flow, now),
    )
    conn.execute(
        "UPDATE house_status SET last_seen = ?, node_online = 1 WHERE house_id = ?",
        (now, house_id),
    )
    conn.commit()
    conn.close()


def update_status(house_id, new_status):
    """Change status only when it differs. A change restarts the issue timer and
    clears the notified flags; returning to normal clears tracking entirely."""
    conn = get_conn()
    row = conn.execute(
        "SELECT current_status FROM house_status WHERE house_id = ?", (house_id,)
    ).fetchone()
    if row is None:
        conn.execute("INSERT INTO house_status (house_id) VALUES (?)", (house_id,))
        current = "normal"
    else:
        current = row["current_status"]
    if current != new_status:
        start = None if new_status == "normal" else _now()
        conn.execute(
            """UPDATE house_status
               SET current_status = ?, issue_start_time = ?,
                   user_notified = 0, municipality_notified = 0
               WHERE house_id = ?""",
            (new_status, start, house_id),
        )
        print(f"[STATUS] house {house_id}: {current} -> {new_status}")
    conn.commit()
    conn.close()


def log_notification(house_id, kind, message):
    conn = get_conn()
    conn.execute(
        "INSERT INTO notifications (house_id, type, message, sent_at) VALUES (?, ?, ?, ?)",
        (house_id, kind, message, _now()),
    )
    conn.commit()
    conn.close()


def mark_notified(house_id, column):
    if column not in ("user_notified", "municipality_notified"):
        raise ValueError("invalid column")
    conn = get_conn()
    conn.execute(f"UPDATE house_status SET {column} = 1 WHERE house_id = ?", (house_id,))
    conn.commit()
    conn.close()


def prune_readings(hours=24):
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=hours)).strftime(TS_FORMAT)
    conn = get_conn()
    conn.execute("DELETE FROM readings WHERE recorded_at < ?", (cutoff,))
    conn.commit()
    conn.close()


# ---------- reads ----------

def get_user(username):
    conn = get_conn()
    row = conn.execute("SELECT * FROM houses WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row


def get_all_statuses_for_escalation():
    conn = get_conn()
    rows = conn.execute(
        """SELECT h.house_id, h.owner_name, h.phone_number, h.address,
                  s.current_status, s.issue_start_time, s.user_notified,
                  s.municipality_notified, s.last_seen, s.node_online
           FROM houses h JOIN house_status s ON s.house_id = h.house_id
           ORDER BY h.house_id"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_overview(house_id=None):
    """Status + latest reading for one house, or for every house."""
    sql = """SELECT h.house_id, h.owner_name, h.address,
                    s.current_status, s.issue_start_time, s.user_notified,
                    s.municipality_notified, s.last_seen, s.node_online,
                    (SELECT pressure FROM readings r WHERE r.house_id = h.house_id
                     ORDER BY r.id DESC LIMIT 1) AS pressure,
                    (SELECT flow FROM readings r WHERE r.house_id = h.house_id
                     ORDER BY r.id DESC LIMIT 1) AS flow
             FROM houses h JOIN house_status s ON s.house_id = h.house_id"""
    params = ()
    if house_id is not None:
        sql += " WHERE h.house_id = ?"
        params = (house_id,)
    sql += " ORDER BY h.house_id"
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def get_recent_readings(house_id, limit=30):
    conn = get_conn()
    rows = conn.execute(
        "SELECT pressure, flow, recorded_at FROM readings WHERE house_id = ? ORDER BY id DESC LIMIT ?",
        (house_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_notifications(house_id=None, kind=None, limit=20):
    sql = "SELECT house_id, type, message, sent_at FROM notifications WHERE 1=1"
    params = []
    if house_id is not None:
        sql += " AND house_id = ?"
        params.append(house_id)
    if kind is not None:
        sql += " AND type = ?"
        params.append(kind)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


# ---------- OTP ----------

def get_house_by_phone(phone):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM houses WHERE phone_number = ? AND role = 'owner'", (phone,)
    ).fetchone()
    conn.close()
    return row


def save_otp(house_id, code_hash, expires_at):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO otp_codes (house_id, code_hash, expires_at, attempts, sent_at) "
        "VALUES (?, ?, ?, 0, ?)",
        (house_id, code_hash, expires_at, _now()),
    )
    conn.commit()
    conn.close()


def get_otp(house_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM otp_codes WHERE house_id = ?", (house_id,)).fetchone()
    conn.close()
    return row


def bump_otp_attempts(house_id):
    conn = get_conn()
    conn.execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE house_id = ?", (house_id,))
    conn.commit()
    conn.close()


def delete_otp(house_id):
    conn = get_conn()
    conn.execute("DELETE FROM otp_codes WHERE house_id = ?", (house_id,))
    conn.commit()
    conn.close()
