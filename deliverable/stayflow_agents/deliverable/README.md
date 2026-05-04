# StayFlow Agents Prototype

A self-contained short-stay rental marketplace demo with:
- Guest, Guest Agent, Host, Host Agent, and Admin roles
- A visible six-stage agent loop: monitor → detect → propose → approve → act → confirm
- Full lifecycle support: inquiry → booking negotiation → check-in → stay → check-out → review
- Agent-to-agent negotiation threads visible in plain language
- Explicit one-tap approvals before any action executes
- Local persistence for returning guests, recurring hosts, listings, bookings, messages, and disputes

## Run locally

From the workspace root:

```bash
python3 -m http.server 8000 --directory deliverable
```

Or, if you `cd deliverable` first:

```bash
python3 -m http.server 8000
```

Then open:

- http://localhost:8000

## Verify

From the workspace root:

```bash
node --test tests/prototype.test.mjs tests/ui-smoke.test.mjs
```

## Demo path

1. Approve the seeded guest proposals.
2. Approve the host counter-offers.
3. Approve the guest counter acceptances.
4. Advance to the check-in day and approve check-in.
5. Report an in-stay issue from the booking card.
6. Reject the host’s recovery proposal to trigger admin escalation.
7. Approve the admin mediation.
8. Advance to checkout and approve checkout + review.

## Files

- `index.html` — app shell
- `styles.css` — UI styling
- `app.mjs` — browser UI + persistence wiring
- `state-engine.mjs` — pure workflow engine shared by the UI and tests
