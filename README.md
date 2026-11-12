# Sakhi Triage Agent (SakhiSafe) - Aerophilia 2026 Agentic AI Hackathon

**Team:** Technova - Prerana Karkal, Preksha Prashant, Sannidhi DS, Aisiri M
**Track:** Claims Triage Agent (adapted: safety-incident triage instead of insurance claims)
**Motto:** Help in one tap, or one word.

## What it does
SakhiSafe captures an SOS (lock-screen tap or the voice phrase "Hello Sakhi") or a smart trigger
(missed check-in, unexpected stop). The agent then triages the incident autonomously:

| Claims Triage track | Sakhi Triage Agent |
|---|---|
| Severity | low / medium / high / critical |
| Coverage | which responders apply (trusted contacts, women helpline 181, police 112) |
| Fraud-risk | false-alarm / accidental-trigger risk |
| Route to right handler | dispatches to the right responder; police/ambulance need user approval |

## Agent loop (planning -> tool use -> action)
1. **Plan** what to check. 2. **Tools:** `get_trip_context`, `get_location_context`,
`assess_false_alarm_risk`, `lookup_responders`. 3. **Decide** severity/coverage/risk.
4. **Act:** `dispatch_alert` (human-in-the-loop approval for escalation). 5. `submit_assessment` (structured JSON).

## Run
```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...            # optional
python agent.py --all --auto-approve            # LLM agent
python agent.py --all --offline --auto-approve  # no-internet fallback
```
All data is mock/sample data. No real alerts are sent.

## AI assistance disclosure
Claude (Anthropic) was used to help design and write the code in this repository.
