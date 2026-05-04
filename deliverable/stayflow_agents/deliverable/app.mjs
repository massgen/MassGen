import {
  addListing,
  addTripRequest,
  advanceDay,
  approveProposal,
  createInitialState,
  getDayLabel,
  getProposalQueue,
  hydrateState,
  rejectProposal,
  reportStayIssue,
  runAllAgentLoops,
  searchListings,
  serializeState,
  summarizeBooking,
} from './state-engine.mjs';

const STORAGE_KEY = 'stayflow-rental-marketplace-v1';
const app = document.querySelector('#app');

const uiState = {
  autoMonitor: true,
  searchCriteria: { city: '', maxNightlyRate: '', partySize: '' },
  toast: 'Prototype loaded. Every action still requires one-tap human approval.',
  lastAutoScan: null,
};

function loadState() {
  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (!saved) {
    const fresh = createInitialState();
    runAllAgentLoops(fresh);
    return fresh;
  }
  const restored = hydrateState(saved);
  runAllAgentLoops(restored);
  return restored;
}

let state = loadState();

function saveState(message) {
  window.localStorage.setItem(STORAGE_KEY, serializeState(state));
  if (message) uiState.toast = message;
}

function resetState() {
  state = createInitialState();
  runAllAgentLoops(state);
  saveState('Demo reset to seeded state.');
  render();
}

function currency(value) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value || 0);
}

function escapeHtml(value = '') {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function commit(message, rerun = true) {
  if (rerun) runAllAgentLoops(state);
  saveState(message);
  render();
}

function groupedQueues() {
  return {
    guest: getProposalQueue(state, 'guest'),
    host: getProposalQueue(state, 'host'),
    admin: getProposalQueue(state, 'admin'),
  };
}

function stats() {
  return {
    pending: getProposalQueue(state).length,
    activeBookings: state.bookings.filter((booking) => ['booked', 'checked_in', 'negotiating', 'inquiry', 'checked_out'].includes(booking.stage)).length,
    disputes: state.bookings.filter((booking) => booking.dispute?.status === 'open').length,
    listings: state.listings.filter((listing) => listing.active !== false).length,
  };
}

function renderProposal(proposal) {
  const accent = proposal.humanRole;
  const trace = proposal.loopTrace || {};
  return `
    <article class="proposal-card ${accent}">
      <div class="badge-row">
        <span class="status-pill" data-status="${escapeHtml(proposal.status)}">${escapeHtml(proposal.status)}</span>
        <span class="tag">${escapeHtml(proposal.agentName)} → ${escapeHtml(proposal.humanName)}</span>
      </div>
      <h3>${escapeHtml(proposal.title)}</h3>
      <p class="helper">${escapeHtml(proposal.description)}</p>
      <div class="thread-tags micro">
        <span class="thread-tag">Monitor: ${escapeHtml(trace.monitor || '—')}</span>
        <span class="thread-tag">Detect: ${escapeHtml(trace.detect || '—')}</span>
        <span class="thread-tag">Propose: ${escapeHtml(trace.propose || '—')}</span>
      </div>
      <div class="inline-actions" style="margin-top:12px;">
        <button class="approve small" data-action="approve-proposal" data-id="${proposal.id}">Approve</button>
        <button class="reject small" data-action="reject-proposal" data-id="${proposal.id}">Reject</button>
      </div>
    </article>
  `;
}

function renderQueue(role, label, proposals) {
  return `
    <section class="queue-column ${role}">
      <header>
        <h2>${label}</h2>
        <span class="badge"><strong>${proposals.length}</strong>&nbsp;pending</span>
      </header>
      ${proposals.length ? proposals.map(renderProposal).join('') : '<div class="empty">No pending approvals. The agent loop will surface the next action automatically.</div>'}
    </section>
  `;
}

function renderListing(listing) {
  const host = state.hosts.find((candidate) => candidate.id === listing.hostId);
  return `
    <article class="listing-card">
      <div class="badge-row">
        <span class="status-pill" data-status="${listing.active ? 'booked' : 'closed'}">${listing.active ? 'active' : 'inactive'}</span>
        <span class="tag">Host: ${escapeHtml(host?.name || 'Unknown')}</span>
        <span class="tag">${escapeHtml(listing.city)}</span>
      </div>
      <h3>${escapeHtml(listing.title)}</h3>
      <div class="price">${currency(listing.nightlyRate)} <span class="muted micro">/ night</span></div>
      <div class="listing-meta micro">
        <span class="tag">Cleaning ${currency(listing.cleaningFee)}</span>
        <span class="tag">Sleeps ${listing.maxGuests}</span>
        <span class="tag">Strategy: ${escapeHtml(listing.availabilityStrategy)}</span>
      </div>
      <p class="helper">${escapeHtml(listing.features.join(' • '))}</p>
      <div class="inline-actions">
        <button class="secondary small" data-action="toggle-listing" data-id="${listing.id}">${listing.active ? 'Pause listing' : 'Reactivate listing'}</button>
        <button class="ghost small" data-action="cycle-strategy" data-id="${listing.id}">Cycle availability mode</button>
      </div>
    </article>
  `;
}

function renderTrip(trip) {
  const booking = state.bookings.find((candidate) => candidate.tripRequestId === trip.id);
  return `
    <article class="trip-card">
      <div class="badge-row">
        <span class="status-pill" data-status="${escapeHtml(trip.status || 'planning')}">${escapeHtml(trip.status || 'planning')}</span>
        <span class="tag">${escapeHtml(trip.city)}</span>
      </div>
      <h3>${escapeHtml(trip.label)}</h3>
      <p class="helper">Day ${trip.startDay} → ${trip.endDay} · Budget ${currency(trip.budget)} · Wants ${escapeHtml(trip.mustHave.join(', '))}</p>
      <p class="micro muted">Check-in preference: ${escapeHtml(trip.checkInPreference)} · ${escapeHtml(trip.specialRequest)}</p>
      ${booking ? `<p class="micro">Linked booking: <strong>${escapeHtml(booking.id)}</strong></p>` : ''}
    </article>
  `;
}

function renderIssuePanel(booking) {
  if (booking.stage !== 'checked_in' || booking.issue) return '';
  return `
    <form data-action="report-issue" data-booking-id="${booking.id}">
      <div class="form-grid compact" style="margin-top:12px;">
        <label>
          Issue summary
          <input name="summary" placeholder="Wi-Fi outage, key problem, cleaning issue..." required />
        </label>
        <label>
          Severity
          <select name="severity">
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="low">Low</option>
          </select>
        </label>
        <label style="align-self:end;">
          <span class="micro">&nbsp;</span>
          <button class="warn full" type="submit">Report in-stay issue</button>
        </label>
      </div>
    </form>
  `;
}

function renderBooking(booking) {
  const item = summarizeBooking(state, booking);
  const issueMarkup = booking.issue
    ? `<div class="alert">Issue: <strong>${escapeHtml(booking.issue.summary)}</strong> · Status <strong>${escapeHtml(booking.issue.status)}</strong>${booking.issue.resolution ? ` · ${escapeHtml(booking.issue.resolution)}` : ''}</div>`
    : '';
  const disputeMarkup = booking.dispute?.status === 'open'
    ? `<div class="alert">Dispute open with admin mediation pending.</div>`
    : '';
  const adjustmentMarkup = booking.financials.adjustments.length
    ? `<p class="micro muted">Adjustments: ${booking.financials.adjustments.map((adj) => `${currency(adj.amount)} for ${escapeHtml(adj.reason)}`).join(' · ')}</p>`
    : '<p class="micro muted">No refunds or credits yet.</p>';
  return `
    <article class="booking-card">
      <div class="badge-row">
        <span class="status-pill" data-status="${escapeHtml(booking.stage)}">${escapeHtml(booking.stage)}</span>
        <span class="tag">${escapeHtml(item.listingTitle || booking.listingId)}</span>
        <span class="tag">Guest: ${escapeHtml(item.guestName || booking.guestId)}</span>
        <span class="tag">Host: ${escapeHtml(item.hostName || booking.hostId)}</span>
      </div>
      <h3>${escapeHtml(item.listingTitle || 'Booking')}</h3>
      <p class="helper">Day ${booking.startDay} (${getDayLabel(state, booking.startDay)}) → Day ${booking.endDay} (${getDayLabel(state, booking.endDay)}) · ${currency(booking.nightlyRate)} nightly · ${currency(booking.financials.payout || booking.total)} total</p>
      <p class="micro muted">Requested check-in: ${escapeHtml(booking.requestedCheckIn || '—')} ${booking.confirmedCheckIn ? `· Confirmed: ${escapeHtml(booking.confirmedCheckIn)}` : ''}</p>
      ${issueMarkup}
      ${disputeMarkup}
      ${adjustmentMarkup}
      ${renderIssuePanel(booking)}
      <div class="thread">
        ${booking.thread.map((message) => `
          <div class="thread-message ${escapeHtml(message.from)}">
            <div class="micro muted">${escapeHtml(message.from)} · day ${message.day}</div>
            <div>${escapeHtml(message.text)}</div>
          </div>
        `).join('')}
      </div>
    </article>
  `;
}

function renderDispute(booking) {
  return `
    <article class="dispute-card">
      <div class="badge-row">
        <span class="status-pill" data-status="${escapeHtml(booking.dispute.status)}">${escapeHtml(booking.dispute.status)}</span>
        <span class="tag">${escapeHtml(state.listings.find((listing) => listing.id === booking.listingId)?.title || booking.listingId)}</span>
      </div>
      <h3>${escapeHtml(booking.issue?.summary || 'No issue summary')}</h3>
      <p class="helper">Guest and host agents could not resolve this case. Admin rules decide the next proposal.</p>
    </article>
  `;
}

function renderActivity(item) {
  return `
    <article class="activity-item">
      <div class="micro muted">Day ${item.day} · ${escapeHtml(item.type)}</div>
      <div>${escapeHtml(item.message)}</div>
    </article>
  `;
}

function currentSearchResults() {
  return searchListings(state, uiState.searchCriteria);
}

function render() {
  const queues = groupedQueues();
  const summary = stats();
  const searchResults = currentSearchResults();
  const openDisputes = state.bookings.filter((booking) => booking.dispute?.status === 'open');
  const bookings = [...state.bookings].sort((a, b) => a.startDay - b.startDay);
  const lastScan = uiState.lastAutoScan ? new Date(uiState.lastAutoScan).toLocaleTimeString() : 'not yet';

  app.innerHTML = `
    <main class="shell">
      <section class="hero">
        <article class="hero-card">
          <div class="hero-badges">
            <span class="badge"><strong>Demo day ${state.currentDay}</strong>&nbsp;(${getDayLabel(state)})</span>
            <span class="badge"><strong>Persistent state</strong>&nbsp;stored in your browser</span>
            <span class="badge"><strong>One tap only</strong>&nbsp;every action waits for explicit approval</span>
          </div>
          <h1>StayFlow Agents</h1>
          <p>
            A working short-stay marketplace prototype where the Guest Agent and Host Agent both monitor,
            detect, propose, wait for explicit human approval, act immediately after approval, and confirm
            the result. Agent-to-agent negotiation, disputes, pricing, turnovers, reviews, and repeat state
            all live in one persistent demo.
          </p>
          <div class="stage-strip" style="margin-top:18px;">
            <span class="stage-pill">1. Monitor</span>
            <span class="stage-pill">2. Detect</span>
            <span class="stage-pill">3. Propose</span>
            <span class="stage-pill">4. Approve</span>
            <span class="stage-pill">5. Act</span>
            <span class="stage-pill">6. Confirm</span>
          </div>
        </article>
        <div class="hero-side">
          <div class="metric-row">
            <article class="metric-card"><span>Pending approvals</span><h3>${summary.pending}</h3></article>
            <article class="metric-card"><span>Active bookings</span><h3>${summary.activeBookings}</h3></article>
            <article class="metric-card"><span>Open disputes</span><h3>${summary.disputes}</h3></article>
            <article class="metric-card"><span>Active listings</span><h3>${summary.listings}</h3></article>
          </div>
          <article class="hero-card">
            <h2 style="margin:0 0 10px;">Live prototype status</h2>
            <p class="helper">${escapeHtml(uiState.toast || '')}</p>
            <p class="micro muted">Auto-monitor: <strong>${uiState.autoMonitor ? 'On' : 'Off'}</strong> · Last scan: ${escapeHtml(lastScan)}</p>
          </article>
        </div>
      </section>

      <section class="controls">
        <div class="control-group">
          <button class="primary" data-action="run-loops">Run all agents now</button>
          <button class="secondary" data-action="advance-day">Advance one demo day</button>
          <button class="secondary" data-action="toggle-auto">${uiState.autoMonitor ? 'Pause auto-monitor' : 'Resume auto-monitor'}</button>
        </div>
        <div class="control-group">
          <button class="ghost" data-action="seed-full-lifecycle">Fast-forward lifecycle</button>
          <button class="reject" data-action="reset-state">Reset demo</button>
        </div>
      </section>

      <section class="queue-grid">
        ${renderQueue('guest', 'Guest approvals', queues.guest)}
        ${renderQueue('host', 'Host approvals', queues.host)}
        ${renderQueue('admin', 'Admin approvals', queues.admin)}
      </section>

      <section class="grid">
        <section class="panel">
          <div class="panel-header">
            <h2>Marketplace search + guest trip planner</h2>
            <span class="micro muted">Returning guest state persists between visits.</span>
          </div>
          <form id="search-form">
            <div class="form-grid compact">
              <label>
                City
                <select name="city">
                  <option value="">All cities</option>
                  <option value="Austin" ${uiState.searchCriteria.city === 'Austin' ? 'selected' : ''}>Austin</option>
                  <option value="Malibu" ${uiState.searchCriteria.city === 'Malibu' ? 'selected' : ''}>Malibu</option>
                </select>
              </label>
              <label>
                Max nightly rate
                <input type="number" name="maxNightlyRate" value="${escapeHtml(uiState.searchCriteria.maxNightlyRate)}" placeholder="450" />
              </label>
              <label>
                Party size
                <input type="number" name="partySize" value="${escapeHtml(uiState.searchCriteria.partySize)}" placeholder="2" min="1" />
              </label>
            </div>
          </form>
          <div style="margin-top:14px;">
            ${searchResults.map(renderListing).join('') || '<div class="empty">No listings match the current guest search.</div>'}
          </div>
          <hr class="sep" />
          <h2 style="margin:0 0 12px;">Add a new guest trip request</h2>
          <form id="trip-form">
            <div class="form-grid">
              <label>Label<input name="label" placeholder="Berlin launch week" required /></label>
              <label>City<input name="city" placeholder="Austin" required /></label>
              <label>Start day<input type="number" name="startDay" min="1" value="5" required /></label>
              <label>End day<input type="number" name="endDay" min="2" value="8" required /></label>
              <label>Budget<input type="number" name="budget" min="100" value="320" required /></label>
              <label>Party size<input type="number" name="partySize" min="1" value="1" required /></label>
              <label>Vibe<input name="vibe" placeholder="work / coastal / family" value="work" /></label>
              <label>Check-in pref<input name="checkInPreference" value="6:00 PM" /></label>
            </div>
            <label style="margin-top:12px;">Must-have features (comma separated)<input name="mustHave" value="fast wifi,self check-in" /></label>
            <label style="margin-top:12px;">Special request<textarea name="specialRequest">Need quiet evening arrival and clear door instructions.</textarea></label>
            <div class="inline-actions" style="margin-top:12px;">
              <button class="primary" type="submit">Add trip request</button>
            </div>
          </form>
          <div style="margin-top:16px;">
            ${state.guests[0].tripRequests.map(renderTrip).join('')}
          </div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <h2>Host listing studio + dynamic pricing</h2>
            <span class="micro muted">Hosts can manage multiple properties at once.</span>
          </div>
          <form id="listing-form">
            <div class="form-grid">
              <label>Title<input name="title" placeholder="Mountain retreat" required /></label>
              <label>City<input name="city" placeholder="Austin" required /></label>
              <label>Nightly rate<input type="number" name="nightlyRate" min="80" value="275" required /></label>
              <label>Cleaning fee<input type="number" name="cleaningFee" min="0" value="45" required /></label>
              <label>Max guests<input type="number" name="maxGuests" min="1" value="2" required /></label>
              <label>Host
                <select name="hostId">
                  ${state.hosts.map((host) => `<option value="${host.id}">${escapeHtml(host.name)}</option>`).join('')}
                </select>
              </label>
            </div>
            <label style="margin-top:12px;">Tags (comma separated)<input name="tags" value="design,work" /></label>
            <label style="margin-top:12px;">Features (comma separated)<input name="features" value="fast wifi,self check-in,parking" /></label>
            <div class="inline-actions" style="margin-top:12px;">
              <button class="primary" type="submit">Create listing</button>
            </div>
          </form>
          <div style="margin-top:16px;">
            ${state.listings.map(renderListing).join('')}
          </div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <h2>Bookings, negotiation threads, and stay monitoring</h2>
            <span class="micro muted">All guest ↔ host agent exchanges stay visible in plain language.</span>
          </div>
          ${bookings.length ? bookings.map(renderBooking).join('') : '<div class="empty">No bookings yet. Approve a guest proposal to start inquiry → booking → check-in → stay → checkout → review.</div>'}
        </section>

        <section class="panel">
          <div class="panel-header">
            <h2>Admin rules, disputes, and audit trail</h2>
            <span class="micro muted">Admins step in only when agents cannot resolve the issue.</span>
          </div>
          <form id="rules-form">
            <div class="form-grid compact">
              <label>
                Dispute credit cap
                <input type="number" name="disputeCreditCap" min="20" value="${state.rules.disputeCreditCap}" />
              </label>
              <label>
                Guest approvals
                <input value="Required" disabled />
              </label>
              <label>
                Host approvals
                <input value="Required" disabled />
              </label>
            </div>
            <div class="inline-actions" style="margin-top:12px;">
              <button class="secondary" type="submit">Update admin rules</button>
            </div>
          </form>
          <div style="margin-top:16px;">
            ${openDisputes.length ? openDisputes.map(renderDispute).join('') : '<div class="empty">No active disputes. Reject a host recovery proposal during a stay to see the admin path.</div>'}
          </div>
          <hr class="sep" />
          <h2 style="margin:0 0 12px;">Marketplace activity</h2>
          <div>
            ${state.activityLog.slice(0, 18).map(renderActivity).join('')}
          </div>
        </section>
      </section>

      <footer class="note">
        Tip: approve the seeded guest proposals, approve the host counters, advance to check-in day, report an issue,
        reject the host recovery, then approve the admin mediation to watch the full lifecycle end to end.
      </footer>
    </main>
  `;
}

function splitList(value) {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function fastForwardLifecycle() {
  const pendingGuest = getProposalQueue(state, 'guest').filter((proposal) => proposal.action.type === 'create_inquiry');
  pendingGuest.forEach((proposal) => approveProposal(state, proposal.id));
  runAllAgentLoops(state);

  getProposalQueue(state, 'host').forEach((proposal) => {
    if (proposal.action.type === 'counter_inquiry') approveProposal(state, proposal.id);
  });
  runAllAgentLoops(state);

  getProposalQueue(state, 'guest').forEach((proposal) => {
    if (proposal.action.type === 'accept_counter') approveProposal(state, proposal.id);
  });

  if (state.bookings[0]) {
    if (state.currentDay < state.bookings[0].startDay) {
      advanceDay(state, state.bookings[0].startDay - state.currentDay);
    }
    runAllAgentLoops(state);
  }

  commit('Fast-forwarded seeded trips to the first check-in window.');
}

app.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const { action, id } = button.dataset;

  if (action === 'approve-proposal') {
    approveProposal(state, id);
    commit('Proposal approved and executed.');
    return;
  }

  if (action === 'reject-proposal') {
    rejectProposal(state, id);
    commit('Proposal rejected. The agent loop will respond with a revised next step.');
    return;
  }

  if (action === 'run-loops') {
    runAllAgentLoops(state);
    commit('Ran monitor → detect → propose across guest, host, and admin agents.', false);
    return;
  }

  if (action === 'advance-day') {
    advanceDay(state, 1);
    commit(`Advanced to day ${state.currentDay}.`);
    return;
  }

  if (action === 'toggle-auto') {
    uiState.autoMonitor = !uiState.autoMonitor;
    render();
    return;
  }

  if (action === 'reset-state') {
    resetState();
    return;
  }

  if (action === 'seed-full-lifecycle') {
    fastForwardLifecycle();
    return;
  }

  if (action === 'toggle-listing') {
    const listing = state.listings.find((candidate) => candidate.id === id);
    listing.active = !listing.active;
    commit(`${listing.title} is now ${listing.active ? 'active' : 'inactive'}.`, false);
    return;
  }

  if (action === 'cycle-strategy') {
    const listing = state.listings.find((candidate) => candidate.id === id);
    const modes = ['normal', 'underbooked', 'premium'];
    const index = modes.indexOf(listing.availabilityStrategy);
    listing.availabilityStrategy = modes[(index + 1) % modes.length];
    commit(`${listing.title} availability strategy is now ${listing.availabilityStrategy}.`, true);
  }
});

app.addEventListener('submit', (event) => {
  event.preventDefault();
  const form = event.target;

  if (form.id === 'trip-form') {
    const data = new FormData(form);
    addTripRequest(state, {
      guestId: state.guests[0].id,
      label: data.get('label'),
      city: data.get('city'),
      startDay: data.get('startDay'),
      endDay: data.get('endDay'),
      budget: data.get('budget'),
      partySize: data.get('partySize'),
      vibe: data.get('vibe'),
      mustHave: splitList(data.get('mustHave') || ''),
      checkInPreference: data.get('checkInPreference'),
      specialRequest: data.get('specialRequest'),
    });
    form.reset();
    commit('Added a new trip request and re-ran the guest agent for matching.', true);
    return;
  }

  if (form.id === 'listing-form') {
    const data = new FormData(form);
    addListing(state, {
      hostId: data.get('hostId'),
      title: data.get('title'),
      city: data.get('city'),
      nightlyRate: data.get('nightlyRate'),
      cleaningFee: data.get('cleaningFee'),
      maxGuests: data.get('maxGuests'),
      tags: splitList(data.get('tags') || ''),
      features: splitList(data.get('features') || ''),
    });
    form.reset();
    commit('Listing created and host portfolio updated.', true);
    return;
  }

  if (form.id === 'rules-form') {
    const data = new FormData(form);
    state.rules.disputeCreditCap = Number(data.get('disputeCreditCap'));
    commit('Admin rule updated for future dispute proposals.', false);
    return;
  }

  if (form.dataset.action === 'report-issue') {
    const data = new FormData(form);
    reportStayIssue(state, {
      bookingId: form.dataset.bookingId,
      summary: data.get('summary'),
      severity: data.get('severity'),
    });
    commit('Reported an in-stay issue and queued the host response.', true);
  }
});

app.addEventListener('input', (event) => {
  const form = event.target.closest('#search-form');
  if (!form) return;
  const data = new FormData(form);
  uiState.searchCriteria = {
    city: data.get('city') || '',
    maxNightlyRate: data.get('maxNightlyRate') || '',
    partySize: data.get('partySize') || '',
  };
  render();
});

window.setInterval(() => {
  if (!uiState.autoMonitor) return;
  const before = getProposalQueue(state).length;
  runAllAgentLoops(state);
  const after = getProposalQueue(state).length;
  uiState.lastAutoScan = Date.now();
  if (after !== before) {
    saveState('Auto-monitor detected a new action and queued it for approval.');
    render();
  }
}, 12000);

saveState('Prototype loaded. Every action still requires one-tap human approval.');
render();
