"""Tools the Sakhi Triage Agent can call. All data is MOCK / sample data."""
import json
from pathlib import Path

DATA = json.loads((Path(__file__).parent / "data" / "mock_data.json").read_text())
OUTBOX = []  # simulated sent alerts (nothing real is ever sent)


def get_trip_context(user_id: str) -> dict:
    u = DATA["users"].get(user_id)
    if not u:
        return {"error": f"unknown user {user_id}"}
    return {"name": u["name"], "trusted_contacts": u["trusted_contacts"], "trip": u["trip"]}


def get_location_context(area: str, timestamp: str) -> dict:
    z = DATA["zones"].get(area)
    if not z:
        return {"error": f"unknown area {area}"}
    hour = int(timestamp.split(":")[0])
    return {**z, "is_night": hour >= 19 or hour < 6, "nearest_safe_places": z["nearby_places"]}


def assess_false_alarm_risk(user_id: str, trigger_type: str, voice_confidence, cancelled_by_user: bool) -> dict:
    """Plays the role of 'fraud-risk' in the Claims Triage track: how likely is this a false/accidental alarm?"""
    u = DATA["users"].get(user_id)
    if not u:
        return {"error": f"unknown user {user_id}"}
    risk, factors = 0.1, []
    acc = u["history"]["accidental_triggers_last_30d"]
    if acc:
        risk += min(0.15 * acc, 0.6)
        factors.append(f"{acc} accidental triggers in last 30 days")
    if voice_confidence is not None and voice_confidence < 0.6:
        risk += 0.3
        factors.append("low voice-match confidence")
    if cancelled_by_user:
        risk += 0.5
        factors.append("user cancelled during countdown")
    if u["trip"]["missed_checkins"] > 0 or u["trip"]["unexpected_stop_minutes"] >= 10:
        risk -= 0.2
        factors.append("corroborating trip anomalies (missed check-in / unexpected stop)")
    return {"false_alarm_risk": round(max(0.0, min(risk, 1.0)), 2), "factors": factors}


def lookup_responders(need: str) -> dict:
    r = DATA["responders"].get(need)
    return r if r else {"error": f"unknown responder '{need}'", "available": list(DATA["responders"])}


APPROVAL_REQUIRED = {"police", "ambulance"}


def dispatch_alert(target: str, message: str, approver=None) -> dict:
    """Simulated dispatch. Escalating to police/ambulance needs human (user) approval."""
    if target in APPROVAL_REQUIRED:
        ok = approver(target, message) if approver else False
        if not ok:
            return {"status": "pending_human_approval", "target": target}
    OUTBOX.append({"target": target, "message": message})
    return {"status": "sent (simulated)", "target": target}


TOOL_SCHEMAS = [
    {"name": "get_trip_context", "description": "Get the user's trusted contacts, trip route, check-in status and unexpected-stop info.",
     "input_schema": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}},
    {"name": "get_location_context", "description": "Get risk score, lighting, crowd and nearest safe places for the incident area at the given time.",
     "input_schema": {"type": "object", "properties": {"area": {"type": "string"}, "timestamp": {"type": "string", "description": "HH:MM"}}, "required": ["area", "timestamp"]}},
    {"name": "assess_false_alarm_risk", "description": "Estimate probability (0-1) that the alert is accidental/false, using user history and trigger signals.",
     "input_schema": {"type": "object", "properties": {"user_id": {"type": "string"}, "trigger_type": {"type": "string"},
                      "voice_confidence": {"type": ["number", "null"]}, "cancelled_by_user": {"type": "boolean"}},
                      "required": ["user_id", "trigger_type", "cancelled_by_user"]}},
    {"name": "lookup_responders", "description": "Look up an official responder number. need is one of: police, women_helpline, women_in_distress, ambulance, campus_security.",
     "input_schema": {"type": "object", "properties": {"need": {"type": "string"}}, "required": ["need"]}},
    {"name": "dispatch_alert", "description": "Send an alert. target: trusted_contacts, user_check, police, ambulance. police/ambulance require human approval and may come back pending.",
     "input_schema": {"type": "object", "properties": {"target": {"type": "string"}, "message": {"type": "string"}}, "required": ["target", "message"]}},
    {"name": "submit_assessment", "description": "FINAL step. Submit the structured triage result after all actions are done.",
     "input_schema": {"type": "object", "properties": {
         "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
         "coverage": {"type": "array", "items": {"type": "string"}, "description": "Which responders/services cover this incident"},
         "false_alarm_risk": {"type": "number"},
         "routed_to": {"type": "array", "items": {"type": "string"}},
         "summary": {"type": "string"}},
         "required": ["severity", "coverage", "false_alarm_risk", "routed_to", "summary"]}},
]
