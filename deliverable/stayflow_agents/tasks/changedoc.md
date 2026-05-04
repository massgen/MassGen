# Change Document

**Based on:** original — final consolidated deliverable

## Summary
Delivered a self-contained prototype of a short-stay rental marketplace with dedicated Guest Agent, Host Agent, and Admin Agent workflows. The app demonstrates the full inquiry → negotiation → booking → check-in → stay monitoring → dispute escalation → check-out → review lifecycle, requires explicit one-tap human approval before every action, preserves state across sessions with browser persistence, supports multiple guest stays and multiple host properties, and keeps all agent-to-agent exchanges visible in plain language.

## Decisions

### DEC-001: Build a self-contained browser prototype
**Origin:** agent1.1 — NEW
**Choice:** Implement the product as a static HTML/CSS/JavaScript app with local persistence instead of a separate backend service.
**Why:** A static browser prototype is the fastest way to demonstrate the full marketplace lifecycle, approval UX, and repeated sessions while remaining easy to run locally and verify.
**Alternatives considered:**
- Full backend/API stack: rejected because it adds infrastructure overhead without improving the prototype goals.
- CLI simulation: rejected because approval taps, proposal queues, and visible negotiation are clearer in a UI.
**Implementation:**
- `deliverable/index.html` — application shell
- `deliverable/styles.css` — interface styling for proposal queues, marketplace panels, and lifecycle cards
- `deliverable/app.mjs` — browser bootstrap, persistence wiring, rendering, event handling, auto-monitor loop
- `deliverable/README.md` — local run and demo instructions

### DEC-002: Make the six-stage agent loop explicit in every proposal
**Origin:** agent1.1 — NEW
**Choice:** Every agent action is represented as a proposal card backed by the same monitor → detect → propose → approve → act → confirm loop.
**Why:** The task centers on agent behavior with human approval. Making the loop visible proves that no action executes until a human explicitly approves it.
**Alternatives considered:**
- Hidden background automation with generic notifications: rejected because it obscures how the agents operate and weakens the demo.
**Implementation:**
- `deliverable/state-engine.mjs` — `buildLoopTrace()`, `runGuestAgentLoop()`, `runHostAgentLoop()`, `runAdminAgentLoop()`
- `deliverable/app.mjs` — `renderProposal()`, grouped approval queues, approve/reject button wiring

### DEC-003: Separate pure state transitions from the DOM layer
**Origin:** agent1.1 — NEW
**Choice:** Keep marketplace rules, booking transitions, approvals, disputes, pricing, turnovers, and serialization in a standalone state engine imported by the UI.
**Why:** Separating state logic from rendering keeps the implementation easier to test, reason about, and extend.
**Alternatives considered:**
- Single monolithic browser script: rejected because it would make lifecycle logic harder to verify and reuse.
**Implementation:**
- `deliverable/state-engine.mjs` — core state creation, agent loops, approval/rejection handlers, persistence helpers
- `deliverable/app.mjs` — UI-only orchestration and browser interaction layer
- `tests/prototype.test.mjs` — state-engine lifecycle coverage
- `tests/ui-smoke.test.mjs` — browser-module smoke coverage with DOM stubs

### DEC-004: Seed the prototype with realistic multi-role, multi-property data
**Origin:** agent1.1 — NEW
**Choice:** Start the prototype with a returning guest, multiple trip requests, multiple hosts, multiple listings, and admin rules, while still allowing live creation of new trip requests and listings.
**Why:** Seeded data makes the marketplace immediately demoable and proves multi-stay and multi-property support without setup friction.
**Alternatives considered:**
- Empty initial state: rejected because it slows down evaluation of the full lifecycle.
**Implementation:**
- `deliverable/state-engine.mjs` — `createInitialState()`, `addTripRequest()`, `addListing()`
- `deliverable/app.mjs` — guest trip planner form and host listing studio form

### DEC-005: Use a demo-day simulation to drive lifecycle events deterministically
**Origin:** agent1.1 — NEW
**Choice:** Represent time as numbered demo days and trigger arrival, stay, checkout, turnover, pricing, and review proposals from stateful day advancement.
**Why:** Deterministic demo time makes the full lifecycle easy to reproduce quickly without waiting on real clocks or background jobs.
**Alternatives considered:**
- Real-time waiting: rejected because it is slower and less reliable for demos and tests.
**Implementation:**
- `deliverable/state-engine.mjs` — `advanceDay()`, date labeling, day-based lifecycle detection
- `deliverable/app.mjs` — advance-day controls and fast-forward lifecycle helper

### DEC-006: Keep agent-to-agent exchanges attached to each booking in plain language
**Origin:** agent1.1 — NEW
**Choice:** Store negotiation, service recovery, escalation, and admin mediation messages directly on the booking thread and render them inline.
**Why:** The requirement explicitly says all agent-to-agent exchanges must remain visible to both humans in plain language.
**Alternatives considered:**
- Detached inbox or hidden logs: rejected because it breaks lifecycle context and makes approvals less legible.
**Implementation:**
- `deliverable/state-engine.mjs` — `addThreadMessage()`, booking creation, negotiation handlers, dispute handlers
- `deliverable/app.mjs` — `renderBooking()` thread rendering

### DEC-007: Cover the critical lifecycle with automated verification
**Origin:** agent1.1 — NEW
**Choice:** Verify the prototype with automated Node tests for negotiation, escalation, persistence, multi-stay support, dynamic pricing, and UI smoke behavior.
**Why:** The prototype is stateful and approval-driven, so automated checks provide strong evidence that the end-to-end flows work as intended.
**Alternatives considered:**
- Manual-only verification: rejected because it is less repeatable and easier to miss lifecycle regressions.
**Implementation:**
- `tests/prototype.test.mjs` — booking negotiation, dispute escalation, persistence, dynamic pricing, concurrent booking tests
- `tests/ui-smoke.test.mjs` — UI render and click-through smoke test
- `.massgen_scratch/verification/final/node-tests.log` — final local test run output
- `.massgen_scratch/verification/final/http-smoke.txt` — static server smoke note

## Deliberation Trail
- agent1.1 introduced the static browser prototype direction and rejected a heavier backend because a self-contained UI better demonstrates approval-driven agent workflows.
- agent1.1 made the six-stage loop a first-class UI concept rather than a hidden internal process so reviewers can see each proposal’s reasoning and approval boundary.
- agent1.1 split the solution into a pure workflow/state module and a browser UI layer, which enabled the final deliverable to preserve the same logic in both the demo and the tests.
- agent1.1 chose seeded multi-role demo data plus editable live state so the final product could immediately show multiple concurrent stays, recurring hosts, and persistent user history.
- agent1.1 anchored lifecycle progress to numbered demo days, which became the final mechanism for deterministic check-in, stay, checkout, turnover, and review proposals.
- agent1.1 attached visible booking threads to negotiations and disputes, and the final deliverable keeps that design unchanged because it is the clearest way to satisfy the plain-language transparency requirement.
- The final consolidation preserves all of those decisions and updates implementation references to this workspace’s delivered files.
