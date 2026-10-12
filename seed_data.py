"""
Creates the 16 houses and the municipality login. Safe to call repeatedly (INSERT OR IGNORE).
Owners sign in with their mobile number + OTP, or user1..user16 + the password set in OWNER_PASSWORDS.
Municipality login: municipality / <MUNICIPALITY_PASSWORD env, default admin123>
"""
from werkzeug.security import generate_password_hash
import config
import db


def seed():
    db.init_db()
    # Hash once, BEFORE opening the database for writing: hashing is slow on small servers and
    # must not happen while the database is locked or delay start-up 16 more times.
    municipality_hash = generate_password_hash(config.MUNICIPALITY_PASSWORD)
    conn = db.get_conn()
    for i in range(1, 17):
        conn.execute(
            """INSERT OR IGNORE INTO houses (house_id, owner_name, phone_number, address, username, password_hash, role)
               VALUES (?, ?, ?, ?, ?, ?, 'owner')""",
            (i, f"Owner {i}", f"+9199999000{i:02d}", f"House {i}, Sample Street",
             f"user{i}", "!"),     # "!" = no stored password; owner passwords come from OWNER_PASSWORDS
        )
        conn.execute("INSERT OR IGNORE INTO house_status (house_id) VALUES (?)", (i,))
    conn.execute(
        """INSERT OR IGNORE INTO houses (house_id, owner_name, username, password_hash, role)
           VALUES (100, 'Municipality Office', 'municipality', ?, 'municipality')""",
        (municipality_hash,),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    seed()
    print("Seed data created.")
