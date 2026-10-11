"""
Put each owner's real mobile number on their house (node id).

  Locally:   python manage_owners.py set 5 --phone 9876543210 --name "R. Kumar" --address "5, Gandhi St"
             python manage_owners.py list
  On Render: set the OWNER_PHONES environment variable, e.g.  1:9876543210,2:9123456780
             (applied every time the app starts, so it survives free-tier resets)
"""
import argparse
import sqlite3



import config
import db
import otp


def set_owner(node_id, phone=None, name=None, address=None):
    conn = db.get_conn()
    try:
        if phone:
            conn.execute("UPDATE houses SET phone_number = ? WHERE house_id = ? AND role = 'owner'", (phone, node_id))
        if name:
            conn.execute("UPDATE houses SET owner_name = ? WHERE house_id = ? AND role = 'owner'", (name, node_id))
        if address:
            conn.execute("UPDATE houses SET address = ? WHERE house_id = ? AND role = 'owner'", (address, node_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        print(f"[OWNERS] phone {phone} already belongs to another house")
        return False
    finally:
        conn.close()


def apply_env_phones():
    for part in (p.strip() for p in config.OWNER_PHONES.split(",")):
        if not part:
            continue
        try:
            node, phone = part.split(":", 1)
            node = int(node)
        except ValueError:
            print(f"[OWNERS] ignoring '{part}' (use node:phone)")
            continue
        norm = otp.normalize_phone(phone)
        if norm is None or not 1 <= node <= 16:
            print(f"[OWNERS] ignoring '{part}' (bad node or phone)")
            continue
        if set_owner(node, phone=norm):
            print(f"[OWNERS] node {node} -> {norm}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("node_id", type=int)
    s.add_argument("--phone")
    s.add_argument("--name")
    s.add_argument("--address")
    sub.add_parser("list")
    args = ap.parse_args()
    db.init_db()
    if args.cmd == "set":
        phone = otp.normalize_phone(args.phone) if args.phone else None
        if args.phone and not phone:
            raise SystemExit("Invalid phone number")
        print("Saved." if set_owner(args.node_id, phone, args.name, args.address) else "Not saved.")
    else:
        for r in db.get_overview():
            u = db.get_conn().execute("SELECT phone_number FROM houses WHERE house_id=?", (r["house_id"],)).fetchone()
            print(r["house_id"], r["owner_name"], u["phone_number"], r["address"])
