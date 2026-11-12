"""Sakhi Triage Agent - planning -> tool-use -> action loop.

Adapted from the 'Claims Triage Agent' track: reads a safety-incident submission and returns
severity, coverage (which responders apply) and false-alarm (fraud-style) risk, then routes it.

Run:
  python agent.py --incident inc1            # LLM agent (needs ANTHROPIC_API_KEY)
  python agent.py --incident inc1 --offline  # rule-based fallback, no internet needed
  python agent.py --all --auto-approve
"""
import argparse, json, os
from pathlib import Path
import tools

MODEL = os.environ.get("SAKHI_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 10

SYSTEM = """You are Sakhi Triage Agent, a women's-safety incident triage agent (MOCK DATA ONLY).
Given an SOS / incident submission, work in this order and be autonomous:
1. PLAN: write 2-4 lines on what you need to check.
2. INVESTIGATE with tools: get_trip_context, get_location_context, assess_false_alarm_risk.
3. DECIDE severity (low/medium/high/critical), coverage (which responders apply), false-alarm risk.
4. ACT: low -> dispatch_alert(user_check) only; medium -> trusted_contacts; high -> trusted_contacts + lookup_responders
   (women_helpline); critical -> trusted_contacts + police (needs human approval; if pending, say so).
   If false_alarm_risk > 0.6 and nothing corroborates the alert, only ask the user to confirm (user_check).
5. FINISH by calling submit_assessment. Never claim an alert was sent unless dispatch_alert said so.
Explicit voice/button SOS is never ignored lightly: when in doubt, escalate one level and ask for confirmation."""


def log(kind, text):
    print(f"[{kind:<7}] {text}")


def make_approver(auto):
    def approver(target, message):
        if auto:
            log("APPROVE", f"auto-approved escalation to {target}")
            return True
        ans = input(f"  >> Approve escalation to {target.upper()}? (y/n): ").strip().lower()
        return ans == "y"
    return approver


def call_tool(name, args, approver):
    if name == "dispatch_alert":
        return tools.dispatch_alert(args["target"], args["message"], approver)
    fn = getattr(tools, name, None)
    if name == "submit_assessment":
        return {"status": "recorded"}
    return fn(**args) if fn else {"error": f"unknown tool {name}"}


# ---------------- LLM agent ----------------
def run_llm_agent(incident, approver):
    import anthropic
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": "Incident submission:\n" + json.dumps(incident, indent=2)}]
    final = None
    for _ in range(MAX_STEPS):
        resp = client.messages.create(model=MODEL, max_tokens=1500, system=SYSTEM,
                                      tools=tools.TOOL_SCHEMAS, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type == "text" and b.text.strip():
                log("THINK", b.text.strip())
            elif b.type == "tool_use":
                log("TOOL", f"{b.name}({json.dumps(b.input)})")
                out = call_tool(b.name, b.input, approver)
                log("RESULT", json.dumps(out))
                if b.name == "submit_assessment":
                    final = b.input
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out)})
        if final or resp.stop_reason != "tool_use":
            break
        messages.append({"role": "user", "content": results})
    return final


# ---------------- Offline fallback (same tools, rule-based planner) ----------------
def run_offline_agent(inc, approver):
    log("PLAN", "1) trip context 2) location context 3) false-alarm risk 4) decide severity 5) route + dispatch")
    ctx = call_tool("get_trip_context", {"user_id": inc["user_id"]}, approver); log("TOOL", f"get_trip_context -> {json.dumps(ctx)}")
    loc = call_tool("get_location_context", {"area": inc["area"], "timestamp": inc["timestamp"]}, approver); log("TOOL", f"get_location_context -> {json.dumps(loc)}")
    fa = call_tool("assess_false_alarm_risk", {"user_id": inc["user_id"], "trigger_type": inc["trigger_type"],
                   "voice_confidence": inc.get("voice_confidence"), "cancelled_by_user": inc["cancelled_by_user"]}, approver)
    log("TOOL", f"assess_false_alarm_risk -> {json.dumps(fa)}")

    trip = ctx["trip"]
    score = 0
    score += 3 if inc["trigger_type"] in ("voice", "button") else 2
    score += 1 if trip["missed_checkins"] >= 2 else 0
    score += 1 if trip["unexpected_stop_minutes"] >= 10 else 0
    score += 1 if loc["risk_score"] >= 0.7 else 0
    score += 1 if loc["is_night"] else 0
    score -= 2 if fa["false_alarm_risk"] > 0.6 else 0
    severity = "critical" if score >= 6 else "high" if score >= 4 else "medium" if score >= 2 else "low"
    log("DECIDE", f"score={score} -> severity={severity}, false_alarm_risk={fa['false_alarm_risk']}")

    place = loc["nearest_safe_places"][0]
    msg = (f"SakhiSafe alert for {ctx['name']}: {inc['trigger_type']} trigger at {inc['timestamp']} "
           f"in {inc['area']}. Nearest safe place: {place['type']} ({place['distance_m']} m).")
    coverage, routed = [], []

    def send(target):
        r = call_tool("dispatch_alert", {"target": target, "message": msg}, approver)
        log("ACTION", f"dispatch_alert({target}) -> {r['status']}")
        if r["status"].startswith("sent"):
            routed.append(target)

    if severity == "low" or (fa["false_alarm_risk"] > 0.6 and score < 6):
        send("user_check"); coverage = ["user"]
    else:
        send("trusted_contacts"); coverage = ["trusted_contacts"]
        if severity in ("high", "critical"):
            h = call_tool("lookup_responders", {"need": "women_helpline"}, approver)
            coverage.append(f"{h['name']} {h['number']}")
        if severity == "critical":
            p = call_tool("lookup_responders", {"need": "police"}, approver)
            coverage.append(f"{p['name']} {p['number']}")
            send("police")
    summary = f"{severity.upper()} incident ({inc['trigger_type']}); routed to {routed or 'nobody (awaiting user confirmation)'}."
    return {"severity": severity, "coverage": coverage, "false_alarm_risk": fa["false_alarm_risk"],
            "routed_to": routed, "summary": summary}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--incident"); ap.add_argument("--all", action="store_true")
    ap.add_argument("--offline", action="store_true"); ap.add_argument("--auto-approve", action="store_true")
    a = ap.parse_args()
    incidents = json.loads((Path(__file__).parent / "samples" / "incidents.json").read_text())
    chosen = incidents if a.all else [i for i in incidents if i["id"] == a.incident]
    if not chosen:
        raise SystemExit("Pick --incident inc1|inc2|inc3 or --all")
    approver = make_approver(a.auto_approve)
    use_llm = not a.offline and os.environ.get("ANTHROPIC_API_KEY")
    if not use_llm:
        print("(running OFFLINE rule-based planner)\n")
    for inc in chosen:
        print(f"\n=== {inc['id']} : {inc['trigger_type']} @ {inc['timestamp']} ===")
        try:
            res = run_llm_agent(inc, approver) if use_llm else run_offline_agent(inc, approver)
        except Exception as e:  # demo must never die on stage
            log("ERROR", f"LLM path failed ({e}); falling back to offline planner")
            res = run_offline_agent(inc, approver)
        print("\nFINAL ASSESSMENT:\n" + json.dumps(res, indent=2))
        Path(__file__).parent.joinpath("out", f"report_{inc['id']}.json").write_text(json.dumps(res, indent=2))
    print("\nSIMULATED OUTBOX:", json.dumps(tools.OUTBOX, indent=2))


if __name__ == "__main__":
    main()
