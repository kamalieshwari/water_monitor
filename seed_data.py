"""
Creates demo logins. Safe to call repeatedly (INSERT OR IGNORE).
Owner logins: user1 / pass1 ... user16 / pass16
Municipality login: municipality / <MUNICIPALITY_PASSWORD env, default admin123>
"""
from werkzeug.security import generate_password_hash
import config
import db


def seed():
    db.init_db()
    conn = db.get_conn()
    for i in range(1, 17):
        conn.execute(
            """INSERT OR IGNORE INTO houses (house_id, owner_name, phone_number, address, username, password_hash, role)
               VALUES (?, ?, ?, ?, ?, ?, 'owner')""",
            (i, f"Owner {i}", f"+9199999000{i:02d}", f"House {i}, Sample Street",
             f"user{i}", generate_password_hash(f"pass{i}")),
        )
        conn.execute("INSERT OR IGNORE INTO house_status (house_id) VALUES (?)", (i,))
    conn.execute(
        """INSERT OR IGNORE INTO houses (house_id, owner_name, username, password_hash, role)
           VALUES (100, 'Municipality Office', 'municipality', ?, 'municipality')""",
        (generate_password_hash(config.MUNICIPALITY_PASSWORD),),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    seed()
    print("Seed data created.")
