import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createInitialState,
  runAllAgentLoops,
  approveProposal,
  rejectProposal,
  advanceDay,
  reportStayIssue,
  serializeState,
  hydrateState,
} from '../deliverable/state-engine.mjs';

test('supports proposal-driven booking negotiation through confirmation', () => {
  const state = createInitialState();

  runAllAgentLoops(state);
  const guestProposal = state.proposals.find(
    (proposal) => proposal.status === 'pending' && proposal.humanRole === 'guest',
  );

  assert.ok(guestProposal, 'guest agent should propose a booking action');
  approveProposal(state, guestProposal.id);

  const inquiry = state.bookings.find((booking) => booking.stage === 'inquiry');
  assert.ok(inquiry, 'approving guest proposal should create an inquiry');

  runAllAgentLoops(state);
  const hostProposal = state.proposals.find(
    (proposal) =>
      proposal.status === 'pending' &&
      proposal.humanRole === 'host' &&
      proposal.bookingId === inquiry.id,
  );

  assert.ok(hostProposal, 'host agent should react to the inquiry');
  approveProposal(state, hostProposal.id);

  assert.equal(
    state.bookings.find((booking) => booking.id === inquiry.id)?.stage,
    'negotiating',
    'host approval should create a counter or negotiated response',
  );

  runAllAgentLoops(state);
  const guestNegotiationProposal = state.proposals.find(
    (proposal) =>
      proposal.status === 'pending' &&
      proposal.humanRole === 'guest' &&
      proposal.bookingId === inquiry.id &&
      proposal.action.type === 'accept_counter',
  );

  assert.ok(guestNegotiationProposal, 'guest agent should bring back the host counter');
  approveProposal(state, guestNegotiationProposal.id);

  const confirmed = state.bookings.find((booking) => booking.id === inquiry.id);
  assert.equal(confirmed.stage, 'booked');
  assert.ok(
    confirmed.thread.some((message) => message.from === 'hostAgent'),
    'agent-to-agent messages should be recorded visibly',
  );
});

test('runs full in-stay issue escalation to admin and back to resolution', () => {
  const state = createInitialState();
  runAllAgentLoops(state);
  approveProposal(
    state,
    state.proposals.find((proposal) => proposal.status === 'pending' && proposal.humanRole === 'guest').id,
  );
  runAllAgentLoops(state);
  approveProposal(
    state,
    state.proposals.find((proposal) => proposal.status === 'pending' && proposal.humanRole === 'host').id,
  );
  runAllAgentLoops(state);
  approveProposal(
    state,
    state.proposals.find(
      (proposal) => proposal.status === 'pending' && proposal.action.type === 'accept_counter',
    ).id,
  );

  const booking = state.bookings[0];
  advanceDay(state, booking.startDay - state.currentDay);
  runAllAgentLoops(state);
  approveProposal(
    state,
    state.proposals.find(
      (proposal) => proposal.status === 'pending' && proposal.action.type === 'check_in_guest',
    ).id,
  );

  reportStayIssue(state, {
    bookingId: booking.id,
    summary: 'Wi‑Fi outage blocks remote work',
    severity: 'high',
  });

  runAllAgentLoops(state);
  const hostIssueProposal = state.proposals.find(
    (proposal) => proposal.status === 'pending' && proposal.action.type === 'offer_issue_resolution',
  );
  assert.ok(hostIssueProposal, 'host agent should propose an issue response');
  rejectProposal(state, hostIssueProposal.id);

  runAllAgentLoops(state);
  const guestEscalation = state.proposals.find(
    (proposal) => proposal.status === 'pending' && proposal.action.type === 'escalate_dispute',
  );
  assert.ok(guestEscalation, 'guest agent should propose escalating unresolved issues');
  approveProposal(state, guestEscalation.id);

  runAllAgentLoops(state);
  const adminProposal = state.proposals.find(
    (proposal) => proposal.status === 'pending' && proposal.humanRole === 'admin',
  );
  assert.ok(adminProposal, 'admin should receive a mediation proposal');
  approveProposal(state, adminProposal.id);

  const resolvedBooking = state.bookings.find((candidate) => candidate.id === booking.id);
  assert.equal(resolvedBooking.issue.status, 'resolved');
  assert.equal(resolvedBooking.dispute.status, 'closed');
  assert.ok(resolvedBooking.financials.adjustments.length > 0, 'resolution should create a refund or credit');
});

test('supports multiple concurrent stays, dynamic pricing proposals, and persistence', () => {
  const state = createInitialState();
  runAllAgentLoops(state);

  const initialGuestProposals = state.proposals.filter(
    (proposal) => proposal.status === 'pending' && proposal.humanRole === 'guest',
  );
  assert.ok(initialGuestProposals.length >= 2, 'seeded state should allow multiple stay proposals');

  for (const proposal of initialGuestProposals.slice(0, 2)) {
    approveProposal(state, proposal.id);
  }

  runAllAgentLoops(state);
  for (const proposal of state.proposals.filter(
    (candidate) => candidate.status === 'pending' && candidate.humanRole === 'host',
  )) {
    approveProposal(state, proposal.id);
  }

  runAllAgentLoops(state);
  for (const proposal of state.proposals.filter(
    (candidate) => candidate.status === 'pending' && candidate.action.type === 'accept_counter',
  )) {
    approveProposal(state, proposal.id);
  }

  const bookedTrips = state.bookings.filter((booking) => booking.stage === 'booked');
  assert.ok(bookedTrips.length >= 2, 'guest should be able to maintain multiple active bookings');

  state.listings.forEach((listing) => {
    listing.availabilityStrategy = 'underbooked';
  });
  runAllAgentLoops(state);
  assert.ok(
    state.proposals.some(
      (proposal) => proposal.status === 'pending' && proposal.action.type === 'adjust_price',
    ),
    'host agent should propose pricing updates',
  );

  const restored = hydrateState(serializeState(state));
  assert.equal(restored.bookings.length, state.bookings.length);
  assert.equal(restored.listings.length, state.listings.length);
  assert.equal(restored.activityLog.length, state.activityLog.length);
});
