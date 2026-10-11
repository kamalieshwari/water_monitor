"""
Water-status rules. Same constants and conditions as the ESP32 firmware.

  leakageCondition = (flow >= LEAKAGE_FLOW_THRESHOLD)
                     && (pressure > 0)
                     && (pressure < LEAKAGE_PRESSURE_THRESHOLD)
  noWaterCondition = (flow == 0.0) && (pressure == 0.0)
"""
MAX_FLOW = 20.0
MAX_PRESSURE = 200.0

FLOW_THRESHOLD = 0.5
PRESSURE_THRESHOLD = 5.0

LEAKAGE_FLOW_THRESHOLD = 6.0
LEAKAGE_PRESSURE_THRESHOLD = 50.0


def clean_reading(pressure, flow):
    """Limit to the sensor range, and treat values below the noise thresholds as 0.
    (This is what makes the exact '== 0.0' no-water test work on real sensors.)"""
    pressure = min(max(pressure, 0.0), MAX_PRESSURE)
    flow = min(max(flow, 0.0), MAX_FLOW)
    if flow < FLOW_THRESHOLD:
        flow = 0.0
    if pressure < PRESSURE_THRESHOLD:
        pressure = 0.0
    return pressure, flow


def classify(pressure, flow):
    """Takes a cleaned reading, returns: normal / possible_leak / no_supply."""
    leakage_condition = (
        (flow >= LEAKAGE_FLOW_THRESHOLD)
        and (pressure > 0)
        and (pressure < LEAKAGE_PRESSURE_THRESHOLD)
    )
    no_water_condition = (flow == 0.0) and (pressure == 0.0)

    if no_water_condition:
        return "no_supply"
    if leakage_condition:
        return "possible_leak"
    return "normal"
