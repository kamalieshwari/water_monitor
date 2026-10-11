"""
Sends SMS. Choose the provider with SMS_PROVIDER:
  console - prints the message in the server log (default; for testing)
  twilio  - Twilio REST API (free-text messages)
  msg91   - MSG91 Flow API (needs DLT-approved templates in India)
Functions never raise: they return True if the provider accepted the message.
"""
import base64
import json
import urllib.error
import urllib.parse
import urllib.request

import config


def _post(req):
    with urllib.request.urlopen(req, timeout=10) as resp:
        return 200 <= resp.status < 300


def _twilio(to, text):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Messages.json"
    fields = {"To": to, "Body": text}
    if config.TWILIO_MESSAGING_SERVICE_SID:
        fields["MessagingServiceSid"] = config.TWILIO_MESSAGING_SERVICE_SID
    else:
        fields["From"] = config.TWILIO_FROM
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode())
    token = base64.b64encode(f"{config.TWILIO_ACCOUNT_SID}:{config.TWILIO_AUTH_TOKEN}".encode()).decode()
    req.add_header("Authorization", "Basic " + token)
    return _post(req)


def _msg91(to, template_id, variables):
    body = {
        "template_id": template_id,
        "short_url": "0",
        "recipients": [{"mobiles": to.lstrip("+"), **variables}],
    }
    if config.MSG91_SENDER_ID:
        body["sender"] = config.MSG91_SENDER_ID
    req = urllib.request.Request(
        "https://control.msg91.com/api/v5/flow/",
        data=json.dumps(body).encode(),
        headers={"authkey": config.MSG91_AUTHKEY, "content-type": "application/json",
                 "accept": "application/json"},
    )
    return _post(req)


def _dispatch(to, text, template_id, variables):
    if not to:
        print("[SMS] no phone number, not sent")
        return False
    provider = config.SMS_PROVIDER
    try:
        if provider == "twilio":
            return _twilio(to, text)
        if provider == "msg91":
            return _msg91(to, template_id, variables)
        print(f"[SMS:console] to={to}: {text}")
        return True
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"[SMS FAILED] provider={provider} to={to}: {e}")
        return False


def send_otp(to, otp, node_id, minutes):
    text = (f"Your Water Monitor login OTP for Node {node_id} is {otp}. "
            f"Valid for {minutes} minutes. Do not share it.")
    return _dispatch(to, text, config.MSG91_OTP_TEMPLATE_ID,
                     {"VAR1": otp, "VAR2": str(node_id)})


def send_alert(to, text):
    return _dispatch(to, text, config.MSG91_ALERT_TEMPLATE_ID, {"VAR1": text})
