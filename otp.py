"""
One-time-password login for house owners.

  1. Owner types their mobile number.
  2. We find the house (= node id) registered to that number.
  3. We generate a random 6-digit OTP for that node, store only a keyed hash
     (bound to the node id), and SMS the plain OTP to the owner.
  4. Owner types the OTP; if it matches and has not expired, they are logged in.
"""
import datetime
import hashlib
import hmac
import secrets

import config
import db
import sms

OTP_LENGTH = 6
OTP_TTL_MINUTES = 5
RESEND_COOLDOWN_SECONDS = 60
MAX_ATTEMPTS = 5


def normalize_phone(raw):
    """Return the number as +<countrycode><digits>, or None if it doesn't look valid."""
    s = "".join(ch for ch in (raw or "") if ch.isdigit() or ch == "+")
    if s.startswith("+"):
        digits = s[1:]
        return "+" + digits if digits.isdigit() and 10 <= len(digits) <= 15 else None
    if not s.isdigit():
        return None
    if len(s) == 11 and s.startswith("0"):
        s = s[1:]
    cc = config.COUNTRY_CODE
    if len(s) == 10:
        return "+" + cc + s
    if len(s) == len(cc) + 10 and s.startswith(cc):
        return "+" + s
    return None


def _hash(node_id, code):
    msg = f"{node_id}:{code}".encode()
    return hmac.new(config.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def _parse(ts):
    return datetime.datetime.strptime(ts, db.TS_FORMAT)


def request_otp(phone_raw):
    """Returns the normalized phone, or None if the number is malformed.
    The result is the same whether or not the number is registered, so nobody
    can use this form to discover which numbers belong to customers."""
    phone = normalize_phone(phone_raw)
    if not phone:
        return None
    house = db.get_house_by_phone(phone)
    if house is None:
        return phone
    node_id = house["house_id"]

    existing = db.get_otp(node_id)
    if existing:
        age = (datetime.datetime.utcnow() - _parse(existing["sent_at"])).total_seconds()
        if age < RESEND_COOLDOWN_SECONDS:
            return phone                              # too soon: keep the earlier OTP valid

    code = "".join(str(secrets.randbelow(10)) for _ in range(OTP_LENGTH))
    expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=OTP_TTL_MINUTES)
    db.save_otp(node_id, _hash(node_id, code), expires.strftime(db.TS_FORMAT))
    sms.send_otp(phone, code, node_id, OTP_TTL_MINUTES)
    return phone


def verify_otp(phone, code):
    """Returns the house row if the OTP is right, otherwise None."""
    house = db.get_house_by_phone(phone) if phone else None
    if house is None:
        return None
    node_id = house["house_id"]
    rec = db.get_otp(node_id)
    if rec is None:
        return None
    if _parse(rec["expires_at"]) < datetime.datetime.utcnow() or rec["attempts"] >= MAX_ATTEMPTS:
        db.delete_otp(node_id)
        return None
    if hmac.compare_digest(rec["code_hash"], _hash(node_id, (code or "").strip())):
        db.delete_otp(node_id)                        # one-time: cannot be reused
        return house
    if rec["attempts"] + 1 >= MAX_ATTEMPTS:
        db.delete_otp(node_id)
    else:
        db.bump_otp_attempts(node_id)
    return None
