# Household water monitor

16 houses, each with a pressure and flow sensor. Owners see their own house; the municipality sees all 16 as status tiles.

## Who signs in how
| Who | Where | How |
|---|---|---|
| House owner | main page `/login` | mobile number, then a 6-digit OTP (valid 5 min) |
| House owner | `/staff-login` | user name `user1` ... `user16` + that house's password |
| Municipality | `/staff-login` | user name `municipality` + `MUNICIPALITY_PASSWORD` |

With `SMS_PROVIDER=console` the OTP and alerts appear in the Render **Logs** tab instead of being texted.

## Settings (Render > service > Environment)
| Variable | Meaning |
|---|---|
| `MUNICIPALITY_PASSWORD` | password for `municipality` (required) |
| `OWNER_PHONES` | OTP login numbers, `1:9876543210,2:9123456780` (house:mobile) |
| `OWNER_PASSWORDS` | password login, `1:river91,2:lotus44` (house:password, no commas inside a password). Houses not listed cannot use password login |
| `MUNICIPALITY_PHONE` | number for municipality alerts |
| `DEMO_SIMULATOR` | `1` = built-in fake sensors, no broker needed |
| `DEMO_MODE` | `1` = alert timers in minutes (3 / 4 / 6), `0` = days |
| `DEMO_VIA_BROKER` | optional, `1` = send demo readings through the MQTT broker instead |

## Status rules (`rules.py`)
- Leak: flow >= 6 and 0 < pressure < 50. Owner alert after 3 min (3 days when `DEMO_MODE=0`). Never sent to the municipality.
- No water: flow = 0 and pressure = 0. Owner alert after 4, municipality alert after 6.
- A status changes after two matching readings. Each alert is sent once and resets when the house returns to normal.

## Demo
Sign in as `municipality`, open **Demo control**, set a house to Leak or No supply. The municipality tiles and that owner's page change within seconds. Alerts follow at the thresholds above.

## Files
- `app.py` web app, login, APIs, background threads
- `config.py` settings from environment variables
- `db.py`, `schema.sql`, `seed_data.py`, `manage_owners.py` database, tables, demo accounts, owner numbers
- `rules.py`, `escalation.py` classification and timed alerts
- `otp.py`, `sms.py` OTP login and SMS sending (console / Twilio / MSG91)
- `sim_engine.py` fake sensors, `mqtt_helper.py` MQTT client
- `templates/` pages, `static/style.css` styling
- `Procfile`, `render.yaml`, `requirements.txt` deployment

## Deploy
Push everything to GitHub (keep `templates/` and `static/` as folders, with `render.yaml` and `Procfile` at the top level), then on Render choose New > Blueprint and select the repo. Fill in the variables above.

## Real hardware
Set `DEMO_SIMULATOR=0` and `DEMO_MODE=0`. The gateway publishes JSON `{"house_id": 3, "pressure": 42.5, "flow": 7.1}` to `<MQTT_PREFIX>/house03/data`. Real SMS: set `SMS_PROVIDER=twilio` (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`) or `msg91` (`MSG91_AUTHKEY`, `MSG91_SENDER_ID`, `MSG91_OTP_TEMPLATE_ID`, `MSG91_ALERT_TEMPLATE_ID`).

Free-tier note: Render's free disk is wiped on restart, so the database is recreated and re-seeded at startup. The app sleeps after about 15 minutes without visitors.
