const MS_PER_DAY = 24 * 60 * 60 * 1000;

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function addDays(baseDate, dayOffset) {
  const base = new Date(baseDate);
  base.setUTCDate(base.getUTCDate() + dayOffset);
  return base.toISOString().slice(0, 10);
}

function nightlyTotal(booking) {
  return (booking.nightlyRate || 0) * ((booking.endDay || 0) - (booking.startDay || 0));
}

function buildLoopTrace({ actor, monitor, detect, propose }) {
  return {
    actor,
    monitor,
    detect,
    propose,
    approve: 'Awaiting one-tap human approval.',
    act: 'Action will execute immediately after approval.',
    confirm: 'State and messages will update on success.',
  };
}

function ensureCounters(state) {
  state.counters ||= { proposal: 1, booking: 1, message: 1, listing: 100, dispute: 1, adjustment: 1, review: 1, trip: 100 };
  return state.counters;
}

function nextId(state, prefix) {
  const counters = ensureCounters(state);
  counters[prefix] ||= 1;
  const id = `${prefix}-${counters[prefix]++}`;
  return id;
}

function logActivity(state, type, message, meta = {}) {
  state.activityLog.unshift({
    id: nextId(state, 'message'),
    day: state.currentDay,
    type,
    message,
    meta,
    at: Date.now() + Math.floor(Math.random() * 1000),
  });
}

function getGuest(state, guestId) {
  return state.guests.find((guest) => guest.id === guestId);
}

function getHost(state, hostId) {
  return state.hosts.find((host) => host.id === hostId);
}

function getListing(state, listingId) {
  return state.listings.find((listing) => listing.id === listingId);
}

function getBooking(state, bookingId) {
  return state.bookings.find((booking) => booking.id === bookingId);
}

function getTripRequest(state, tripRequestId) {
  for (const guest of state.guests) {
    const found = guest.tripRequests.find((trip) => trip.id === tripRequestId);
    if (found) return found;
  }
  return undefined;
}

function proposalExists(state, matcher) {
  return state.proposals.some((proposal) => proposal.status === 'pending' && matcher(proposal));
}

function bookingForTrip(state, tripRequestId) {
  return state.bookings.find((booking) => booking.tripRequestId === tripRequestId && !['cancelled', 'completed'].includes(booking.stage));
}

function scoreListing(tripRequest, listing) {
  let score = 0;
  if (tripRequest.city === listing.city) score += 5;
  score += Math.max(0, 4 - Math.abs((tripRequest.budget || 0) - listing.nightlyRate) / 50);
  if ((listing.maxGuests || 1) >= (tripRequest.partySize || 1)) score += 2;
  for (const feature of tripRequest.mustHave || []) {
    if (listing.features.includes(feature)) score += 1.5;
  }
  if (listing.tags.includes(tripRequest.vibe)) score += 1.25;
  return score;
}

function matchTripToListing(state, tripRequest) {
  const candidates = state.listings
    .filter((listing) => listing.city === tripRequest.city && listing.active !== false)
    .map((listing) => ({ listing, score: scoreListing(tripRequest, listing) }))
    .sort((a, b) => b.score - a.score);
  return candidates[0]?.listing;
}

function createProposal(state, draft) {
  const proposal = {
    id: nextId(state, 'proposal'),
    createdDay: state.currentDay,
    status: 'pending',
    ...draft,
  };
  state.proposals.unshift(proposal);
  logActivity(
    state,
    'proposal_created',
    `${proposal.agentName} proposed an action for ${proposal.humanName}: ${proposal.title}`,
    { proposalId: proposal.id, humanRole: proposal.humanRole, bookingId: proposal.bookingId || null },
  );
  return proposal;
}

function addThreadMessage(state, booking, from, text, visibility = ['guest', 'host']) {
  booking.thread ||= [];
  booking.thread.push({
    id: nextId(state, 'message'),
    day: state.currentDay,
    from,
    text,
    visibility,
  });
}

function calculatePayout(booking, listing) {
  const nights = Math.max(1, booking.endDay - booking.startDay);
  return booking.nightlyRate * nights + (listing.cleaningFee || 0);
}

function createBookingFromTrip(state, tripRequest, listing) {
  const booking = {
    id: nextId(state, 'booking'),
    guestId: tripRequest.guestId,
    hostId: listing.hostId,
    listingId: listing.id,
    tripRequestId: tripRequest.id,
    stage: 'inquiry',
    lifecycle: 'inquiry',
    startDay: tripRequest.startDay,
    endDay: tripRequest.endDay,
    requestedCheckIn: tripRequest.checkInPreference,
    proposedNightlyRate: Math.min(tripRequest.budget, listing.nightlyRate),
    nightlyRate: listing.nightlyRate,
    total: listing.nightlyRate * (tripRequest.endDay - tripRequest.startDay),
    partySize: tripRequest.partySize,
    specialRequest: tripRequest.specialRequest,
    thread: [],
    issue: null,
    dispute: { status: 'none' },
    financials: { payout: 0, adjustments: [] },
    review: { guestSubmitted: false, hostSubmitted: false },
    turnover: { status: 'pending' },
  };
  state.bookings.push(booking);
  tripRequest.status = 'inquiry_sent';
  tripRequest.bookingId = booking.id;
  addThreadMessage(
    state,
    booking,
    'guestAgent',
    `Inquiry created for ${listing.title}. Requested ${tripRequest.checkInPreference} check-in and noted: ${tripRequest.specialRequest}.`,
  );
  addThreadMessage(
    state,
    booking,
    'system',
    `Both humans can review this plain-language thread before approving next actions.`,
  );
  logActivity(state, 'booking_created', `Guest inquiry opened for ${listing.title}.`, { bookingId: booking.id, listingId: listing.id });
  return booking;
}

function addAdjustment(state, booking, amount, reason, actor = 'admin') {
  booking.financials.adjustments.push({
    id: nextId(state, 'adjustment'),
    amount,
    reason,
    actor,
    day: state.currentDay,
  });
}

function approveGuestBookingProposal(state, proposal) {
  const tripRequest = getTripRequest(state, proposal.action.tripRequestId);
  const listing = getListing(state, proposal.action.listingId);
  if (!tripRequest || !listing) return;
  const booking = createBookingFromTrip(state, tripRequest, listing);
  booking.humanApprovalHistory = [{ by: 'guest', decision: 'approved', proposalId: proposal.id, day: state.currentDay }];
  logActivity(state, 'proposal_approved', `Guest approved booking inquiry for ${listing.title}.`, { proposalId: proposal.id, bookingId: booking.id });
}

function approveHostCounterProposal(state, proposal) {
  const booking = getBooking(state, proposal.bookingId);
  const listing = getListing(state, booking?.listingId);
  if (!booking || !listing) return;
  const counterNightlyRate = proposal.action.counterNightlyRate;
  booking.stage = 'negotiating';
  booking.lifecycle = 'negotiation';
  booking.pendingCounter = {
    nightlyRate: counterNightlyRate,
    checkInTime: proposal.action.checkInTime,
    note: proposal.action.note,
  };
  addThreadMessage(
    state,
    booking,
    'hostAgent',
    `Counter-offer: ${proposal.action.note} ${proposal.action.checkInTime} check-in at $${counterNightlyRate}/night.`,
  );
  booking.humanApprovalHistory ||= [];
  booking.humanApprovalHistory.push({ by: 'host', decision: 'approved', proposalId: proposal.id, day: state.currentDay });
  logActivity(state, 'proposal_approved', `Host approved a counter-offer for booking ${booking.id}.`, { proposalId: proposal.id, bookingId: booking.id });
}

function approveGuestCounterAcceptance(state, proposal) {
  const booking = getBooking(state, proposal.bookingId);
  const listing = getListing(state, booking?.listingId);
  if (!booking || !listing || !booking.pendingCounter) return;
  booking.stage = 'booked';
  booking.lifecycle = 'booked';
  booking.nightlyRate = booking.pendingCounter.nightlyRate;
  booking.confirmedCheckIn = booking.pendingCounter.checkInTime;
  booking.total = booking.nightlyRate * (booking.endDay - booking.startDay);
  booking.financials.payout = calculatePayout(booking, listing);
  booking.pendingCounter = null;
  const tripRequest = getTripRequest(state, booking.tripRequestId);
  if (tripRequest) tripRequest.status = 'booked';
  addThreadMessage(
    state,
    booking,
    'guestAgent',
    `Guest accepted the host counter-offer. Booking is now confirmed.`,
  );
  logActivity(state, 'booking_confirmed', `Booking ${booking.id} is confirmed.`, { bookingId: booking.id });
}

function approveCheckIn(state, proposal) {
  const booking = getBooking(state, proposal.bookingId);
  if (!booking) return;
  booking.stage = 'checked_in';
  booking.lifecycle = 'stay';
  booking.checkedInDay = state.currentDay;
  addThreadMessage(state, booking, 'guestAgent', `Guest checked in using the approved arrival plan.`, ['guest', 'host']);
  logActivity(state, 'check_in', `Guest checked in for booking ${booking.id}.`, { bookingId: booking.id });
}

function approveIssueResolution(state, proposal) {
  const booking = getBooking(state, proposal.bookingId);
  if (!booking || !booking.issue) return;
  booking.issue.status = 'resolved';
  booking.issue.resolvedDay = state.currentDay;
  booking.issue.resolution = proposal.action.resolution;
  addAdjustment(state, booking, proposal.action.creditAmount, proposal.action.resolution, 'host');
  addThreadMessage(state, booking, 'hostAgent', `Resolution applied: ${proposal.action.resolution}. Credit: $${proposal.action.creditAmount}.`);
  logActivity(state, 'issue_resolved', `Host resolved issue for booking ${booking.id}.`, { bookingId: booking.id });
}

function approveDisputeEscalation(state, proposal) {
  const booking = getBooking(state, proposal.bookingId);
  if (!booking || !booking.issue) return;
  booking.dispute = {
    id: nextId(state, 'dispute'),
    status: 'open',
    openedDay: state.currentDay,
    summary: booking.issue.summary,
  };
  booking.issue.status = 'escalated';
  addThreadMessage(state, booking, 'guestAgent', 'Escalating the unresolved issue to marketplace admin for mediation.');
  logActivity(state, 'dispute_opened', `Guest escalated booking ${booking.id} to admin.`, { bookingId: booking.id, disputeId: booking.dispute.id });
}

function approveAdminResolution(state, proposal) {
  const booking = getBooking(state, proposal.bookingId);
  if (!booking || !booking.issue) return;
  booking.dispute.status = 'closed';
  booking.dispute.closedDay = state.currentDay;
  booking.issue.status = 'resolved';
  booking.issue.resolution = proposal.action.resolution;
  booking.issue.resolvedDay = state.currentDay;
  addAdjustment(state, booking, proposal.action.creditAmount, proposal.action.resolution, 'admin');
  addThreadMessage(state, booking, 'admin', `Admin mediation closed the dispute: ${proposal.action.resolution}. Credit approved: $${proposal.action.creditAmount}.`);
  logActivity(state, 'dispute_closed', `Admin resolved dispute for booking ${booking.id}.`, { bookingId: booking.id });
}

function approveCheckout(state, proposal) {
  const booking = getBooking(state, proposal.bookingId);
  if (!booking) return;
  booking.stage = 'checked_out';
  booking.lifecycle = 'review';
  booking.checkedOutDay = state.currentDay;
  booking.turnover.status = 'needed';
  addThreadMessage(state, booking, 'system', 'Guest checked out. Turnover coordination can begin.');
  logActivity(state, 'check_out', `Guest checked out of booking ${booking.id}.`, { bookingId: booking.id });
}

function approveReview(state, proposal) {
  const booking = getBooking(state, proposal.bookingId);
  if (!booking) return;
  booking.review.guestSubmitted = true;
  booking.review.guestReview = {
    id: nextId(state, 'review'),
    rating: 5,
    summary: 'Smooth recovery and clear communication after an issue.',
    day: state.currentDay,
  };
  booking.stage = 'completed';
  booking.lifecycle = 'completed';
  const tripRequest = getTripRequest(state, booking.tripRequestId);
  if (tripRequest) tripRequest.status = 'completed';
  addThreadMessage(state, booking, 'guestAgent', 'Guest review posted and profile preferences updated from outcome.');
  logActivity(state, 'review_submitted', `Guest submitted a review for booking ${booking.id}.`, { bookingId: booking.id });
}

function approveTurnover(state, proposal) {
  const booking = getBooking(state, proposal.bookingId);
  if (!booking) return;
  booking.turnover.status = 'scheduled';
  booking.turnover.scheduledDay = state.currentDay;
  logActivity(state, 'turnover_scheduled', `Turnover scheduled for booking ${booking.id}.`, { bookingId: booking.id });
}

function approvePriceAdjustment(state, proposal) {
  const listing = getListing(state, proposal.action.listingId);
  if (!listing) return;
  listing.nightlyRate = proposal.action.newNightlyRate;
  listing.lastPriceUpdateDay = state.currentDay;
  logActivity(state, 'price_updated', `Host approved pricing update for ${listing.title}.`, { listingId: listing.id });
}

function rejectIssueResolution(state, proposal) {
  const booking = getBooking(state, proposal.bookingId);
  if (!booking || !booking.issue) return;
  booking.issue.lastHostProposalRejected = true;
  booking.issue.status = 'open';
  addThreadMessage(state, booking, 'system', 'Host rejected the proposed resolution; the agent will revise next steps.');
  logActivity(state, 'proposal_rejected', `Host rejected issue resolution proposal for booking ${booking.id}.`, { proposalId: proposal.id, bookingId: booking.id });
}

function genericReject(state, proposal) {
  logActivity(state, 'proposal_rejected', `${proposal.humanName} rejected: ${proposal.title}`, { proposalId: proposal.id, bookingId: proposal.bookingId || null });
}

export function createInitialState() {
  const baseDate = '2026-05-04T00:00:00.000Z';
  return {
    version: 1,
    createdAt: Date.now(),
    baseDate,
    currentDay: 1,
    counters: { proposal: 1, booking: 1, message: 1, listing: 100, dispute: 1, adjustment: 1, review: 1, trip: 100 },
    guests: [
      {
        id: 'guest-1',
        name: 'Maya Chen',
        notes: 'Returning guest who values fast wifi, clear check-in, and flexible problem handling.',
        preferences: { prefersQuiet: true, defaultBudget: 320 },
        tripRequests: [
          {
            id: 'trip-1',
            guestId: 'guest-1',
            label: 'Austin design sprint',
            city: 'Austin',
            startDay: 2,
            endDay: 5,
            budget: 265,
            partySize: 1,
            vibe: 'work',
            mustHave: ['fast wifi', 'self check-in'],
            checkInPreference: '9:00 PM',
            specialRequest: 'Quiet desk setup for late product review.',
            status: 'planning',
          },
          {
            id: 'trip-2',
            guestId: 'guest-1',
            label: 'Malibu family reset',
            city: 'Malibu',
            startDay: 4,
            endDay: 7,
            budget: 410,
            partySize: 2,
            vibe: 'coastal',
            mustHave: ['parking', 'ocean view'],
            checkInPreference: '4:30 PM',
            specialRequest: 'Need child-friendly arrival instructions.',
            status: 'planning',
          },
        ],
      },
    ],
    hosts: [
      { id: 'host-1', name: 'Elena Ruiz', propertyIds: ['listing-1', 'listing-2'] },
      { id: 'host-2', name: 'Marcus Lee', propertyIds: ['listing-3'] },
    ],
    admins: [{ id: 'admin-1', name: 'Jordan Kim' }],
    rules: {
      disputeCreditCap: 180,
      guestApprovalRequired: true,
      hostApprovalRequired: true,
      adminApprovalRequired: true,
    },
    listings: [
      {
        id: 'listing-1',
        hostId: 'host-1',
        title: 'Harbor Loft',
        city: 'Austin',
        neighborhood: 'East Austin',
        nightlyRate: 275,
        cleaningFee: 45,
        maxGuests: 2,
        tags: ['work', 'design'],
        features: ['fast wifi', 'self check-in', 'desk', 'coffee'],
        active: true,
        availabilityStrategy: 'normal',
        occupancyTarget: 0.7,
      },
      {
        id: 'listing-2',
        hostId: 'host-1',
        title: 'Ocean View Bungalow',
        city: 'Malibu',
        neighborhood: 'Point Dume',
        nightlyRate: 395,
        cleaningFee: 65,
        maxGuests: 4,
        tags: ['coastal', 'family'],
        features: ['parking', 'ocean view', 'smart lock', 'washer'],
        active: true,
        availabilityStrategy: 'normal',
        occupancyTarget: 0.8,
      },
      {
        id: 'listing-3',
        hostId: 'host-2',
        title: 'Garden Studio',
        city: 'Austin',
        neighborhood: 'South Congress',
        nightlyRate: 225,
        cleaningFee: 35,
        maxGuests: 2,
        tags: ['work', 'budget'],
        features: ['fast wifi', 'parking', 'patio'],
        active: true,
        availabilityStrategy: 'normal',
        occupancyTarget: 0.6,
      },
    ],
    bookings: [],
    proposals: [],
    activityLog: [
      {
        id: 'seed-1',
        day: 1,
        type: 'system',
        message: 'Seeded demo state loaded with returning guest, multi-property host, and marketplace admin.',
        at: Date.now(),
      },
    ],
  };
}

export function addTripRequest(state, input) {
  const guest = getGuest(state, input.guestId || state.guests[0].id);
  const trip = {
    id: nextId(state, 'trip'),
    guestId: guest.id,
    label: input.label,
    city: input.city,
    startDay: Number(input.startDay),
    endDay: Number(input.endDay),
    budget: Number(input.budget),
    partySize: Number(input.partySize || 1),
    vibe: input.vibe || 'work',
    mustHave: (input.mustHave || []).filter(Boolean),
    checkInPreference: input.checkInPreference || '5:00 PM',
    specialRequest: input.specialRequest || 'Standard arrival details requested.',
    status: 'planning',
  };
  guest.tripRequests.push(trip);
  logActivity(state, 'trip_request_added', `New guest trip request added for ${trip.city}.`, { tripRequestId: trip.id });
  return trip;
}

export function addListing(state, input) {
  const host = getHost(state, input.hostId || state.hosts[0].id);
  const listing = {
    id: nextId(state, 'listing'),
    hostId: host.id,
    title: input.title,
    city: input.city,
    neighborhood: input.neighborhood || 'Custom',
    nightlyRate: Number(input.nightlyRate),
    cleaningFee: Number(input.cleaningFee || 40),
    maxGuests: Number(input.maxGuests || 2),
    tags: (input.tags || []).filter(Boolean),
    features: (input.features || []).filter(Boolean),
    active: true,
    availabilityStrategy: input.availabilityStrategy || 'normal',
    occupancyTarget: Number(input.occupancyTarget || 0.7),
  };
  state.listings.push(listing);
  host.propertyIds.push(listing.id);
  logActivity(state, 'listing_added', `Host added listing ${listing.title}.`, { listingId: listing.id });
  return listing;
}

export function searchListings(state, criteria = {}) {
  return state.listings
    .filter((listing) => listing.active !== false)
    .filter((listing) => !criteria.city || listing.city === criteria.city)
    .filter((listing) => !criteria.maxNightlyRate || listing.nightlyRate <= Number(criteria.maxNightlyRate))
    .filter((listing) => !criteria.partySize || listing.maxGuests >= Number(criteria.partySize))
    .map((listing) => ({ ...listing }));
}

export function advanceDay(state, days = 1) {
  state.currentDay += Number(days);
  for (const booking of state.bookings) {
    if (booking.stage === 'booked' && state.currentDay > booking.startDay) {
      booking.lifecycle = 'arrival_window';
    }
  }
  logActivity(state, 'time_advanced', `Simulation advanced to day ${state.currentDay} (${addDays(state.baseDate, state.currentDay - 1)}).`, { currentDay: state.currentDay });
}

export function reportStayIssue(state, { bookingId, summary, severity = 'medium' }) {
  const booking = getBooking(state, bookingId);
  if (!booking) return;
  booking.issue = {
    status: 'open',
    summary,
    severity,
    reportedDay: state.currentDay,
    resolution: null,
    lastHostProposalRejected: false,
  };
  addThreadMessage(state, booking, 'guestAgent', `Issue detected during stay: ${summary}. Severity: ${severity}.`);
  logActivity(state, 'issue_reported', `Issue reported for booking ${booking.id}.`, { bookingId: booking.id });
}

export function runGuestAgentLoop(state) {
  for (const guest of state.guests) {
    for (const tripRequest of guest.tripRequests) {
      if (tripRequest.status === 'planning' && !bookingForTrip(state, tripRequest.id)) {
        const bestListing = matchTripToListing(state, tripRequest);
        if (bestListing && !proposalExists(state, (proposal) => proposal.action.tripRequestId === tripRequest.id && proposal.action.type === 'create_inquiry')) {
          createProposal(state, {
            humanRole: 'guest',
            humanId: guest.id,
            humanName: guest.name,
            agentName: 'Guest Agent',
            title: `Book ${bestListing.title} for ${tripRequest.label}`,
            description: `Best match found in ${tripRequest.city}: ${bestListing.title} at $${bestListing.nightlyRate}/night with ${tripRequest.mustHave.join(', ')}.`,
            action: {
              type: 'create_inquiry',
              tripRequestId: tripRequest.id,
              listingId: bestListing.id,
            },
            loopTrace: buildLoopTrace({
              actor: 'Guest Agent',
              monitor: 'Watched open trip requests, preferences, and listing inventory.',
              detect: `Detected an unbooked trip request for ${tripRequest.label}.`,
              propose: `Proposed sending a ready-to-go inquiry to ${bestListing.title}.`,
            }),
          });
        }
      }
    }
  }

  for (const booking of state.bookings) {
    const guest = getGuest(state, booking.guestId);
    if (booking.stage === 'negotiating' && booking.pendingCounter && !proposalExists(state, (proposal) => proposal.bookingId === booking.id && proposal.action.type === 'accept_counter')) {
      createProposal(state, {
        humanRole: 'guest',
        humanId: guest.id,
        humanName: guest.name,
        agentName: 'Guest Agent',
        bookingId: booking.id,
        title: `Accept host counter for ${getListing(state, booking.listingId).title}`,
        description: `Host can honor the request with ${booking.pendingCounter.checkInTime} check-in at $${booking.pendingCounter.nightlyRate}/night.`,
        action: { type: 'accept_counter' },
        loopTrace: buildLoopTrace({
          actor: 'Guest Agent',
          monitor: 'Watched booking negotiations and host replies.',
          detect: 'Detected a new host counter-offer requiring guest approval.',
          propose: 'Proposed accepting the revised terms and confirming the stay.',
        }),
      });
    }

    if (booking.stage === 'booked' && state.currentDay >= booking.startDay && !proposalExists(state, (proposal) => proposal.bookingId === booking.id && proposal.action.type === 'check_in_guest')) {
      createProposal(state, {
        humanRole: 'guest',
        humanId: guest.id,
        humanName: guest.name,
        agentName: 'Guest Agent',
        bookingId: booking.id,
        title: `Check in to ${getListing(state, booking.listingId).title}`,
        description: `Arrival window is open. Check in using the approved ${booking.confirmedCheckIn || booking.requestedCheckIn} plan.`,
        action: { type: 'check_in_guest' },
        loopTrace: buildLoopTrace({
          actor: 'Guest Agent',
          monitor: 'Watched confirmed bookings and arrival windows.',
          detect: 'Detected that check-in is due today.',
          propose: 'Proposed executing the confirmed check-in plan.',
        }),
      });
    }

    if (booking.issue?.status === 'open' && booking.issue.lastHostProposalRejected && booking.dispute.status === 'none' && !proposalExists(state, (proposal) => proposal.bookingId === booking.id && proposal.action.type === 'escalate_dispute')) {
      createProposal(state, {
        humanRole: 'guest',
        humanId: guest.id,
        humanName: guest.name,
        agentName: 'Guest Agent',
        bookingId: booking.id,
        title: `Escalate ${getListing(state, booking.listingId).title} issue to admin`,
        description: `The host did not approve the proposed recovery for “${booking.issue.summary}”. Escalate to admin mediation?`,
        action: { type: 'escalate_dispute' },
        loopTrace: buildLoopTrace({
          actor: 'Guest Agent',
          monitor: 'Watched in-stay issues, host decisions, and dispute thresholds.',
          detect: 'Detected an unresolved issue after a failed recovery path.',
          propose: 'Proposed escalating to marketplace admin for mediation.',
        }),
      });
    }

    if (booking.stage === 'checked_in' && state.currentDay >= booking.endDay && !proposalExists(state, (proposal) => proposal.bookingId === booking.id && proposal.action.type === 'check_out_guest')) {
      createProposal(state, {
        humanRole: 'guest',
        humanId: guest.id,
        humanName: guest.name,
        agentName: 'Guest Agent',
        bookingId: booking.id,
        title: `Check out of ${getListing(state, booking.listingId).title}`,
        description: 'Stay has reached checkout day. Complete checkout and trigger final settlement.',
        action: { type: 'check_out_guest' },
        loopTrace: buildLoopTrace({
          actor: 'Guest Agent',
          monitor: 'Watched active stays and checkout windows.',
          detect: 'Detected the stay has reached departure day.',
          propose: 'Proposed checking out and starting the post-stay flow.',
        }),
      });
    }

    if (booking.stage === 'checked_out' && !booking.review.guestSubmitted && !proposalExists(state, (proposal) => proposal.bookingId === booking.id && proposal.action.type === 'submit_review')) {
      createProposal(state, {
        humanRole: 'guest',
        humanId: guest.id,
        humanName: guest.name,
        agentName: 'Guest Agent',
        bookingId: booking.id,
        title: `Submit review for ${getListing(state, booking.listingId).title}`,
        description: 'Review window is open. Post a review and update future travel preferences from the outcome.',
        action: { type: 'submit_review' },
        loopTrace: buildLoopTrace({
          actor: 'Guest Agent',
          monitor: 'Watched completed stays, refunds, and review windows.',
          detect: 'Detected a post-stay review opportunity.',
          propose: 'Proposed submitting a review and learning from the result.',
        }),
      });
    }
  }
}

export function runHostAgentLoop(state) {
  for (const booking of state.bookings) {
    const host = getHost(state, booking.hostId);
    const listing = getListing(state, booking.listingId);
    if (booking.stage === 'inquiry' && !proposalExists(state, (proposal) => proposal.bookingId === booking.id && proposal.action.type === 'counter_inquiry')) {
      const counterNightlyRate = Math.max(booking.proposedNightlyRate, listing.nightlyRate - 10);
      createProposal(state, {
        humanRole: 'host',
        humanId: host.id,
        humanName: host.name,
        agentName: 'Host Agent',
        bookingId: booking.id,
        title: `Respond to inquiry for ${listing.title}`,
        description: `Suggest ${counterNightlyRate}/night and ${booking.requestedCheckIn} self check-in with tailored arrival instructions.`,
        action: {
          type: 'counter_inquiry',
          counterNightlyRate,
          checkInTime: booking.requestedCheckIn,
          note: 'Arrival request works with a slightly adjusted rate and digital guide.',
        },
        loopTrace: buildLoopTrace({
          actor: 'Host Agent',
          monitor: 'Watched new inquiries, pricing, and special requests.',
          detect: 'Detected a guest inquiry requiring a host response.',
          propose: 'Proposed a ready-to-send counter-offer and arrival plan.',
        }),
      });
    }

    if (booking.stage === 'checked_in' && booking.issue?.status === 'open' && booking.dispute.status === 'none' && !proposalExists(state, (proposal) => proposal.bookingId === booking.id && proposal.action.type === 'offer_issue_resolution')) {
      const creditAmount = booking.issue.severity === 'high' ? 90 : 45;
      createProposal(state, {
        humanRole: 'host',
        humanId: host.id,
        humanName: host.name,
        agentName: 'Host Agent',
        bookingId: booking.id,
        title: `Resolve stay issue at ${listing.title}`,
        description: `Offer a ${creditAmount} credit and rapid support for “${booking.issue.summary}”.`,
        action: {
          type: 'offer_issue_resolution',
          creditAmount,
          resolution: `Applied a $${creditAmount} goodwill credit and escalated vendor support.`,
        },
        loopTrace: buildLoopTrace({
          actor: 'Host Agent',
          monitor: 'Watched active stays, guest reports, and service alerts.',
          detect: 'Detected an in-stay issue affecting the guest experience.',
          propose: 'Proposed a concrete service recovery package for host approval.',
        }),
      });
    }

    if (booking.stage === 'checked_out' && booking.turnover.status === 'needed' && !proposalExists(state, (proposal) => proposal.bookingId === booking.id && proposal.action.type === 'schedule_turnover')) {
      createProposal(state, {
        humanRole: 'host',
        humanId: host.id,
        humanName: host.name,
        agentName: 'Host Agent',
        bookingId: booking.id,
        title: `Schedule turnover for ${listing.title}`,
        description: 'Coordinate cleaning and restocking before the next arrival.',
        action: { type: 'schedule_turnover' },
        loopTrace: buildLoopTrace({
          actor: 'Host Agent',
          monitor: 'Watched checkout completions and back-to-back availability.',
          detect: 'Detected turnover work needed between bookings.',
          propose: 'Proposed scheduling cleaners and restocking tasks.',
        }),
      });
    }
  }

  for (const listing of state.listings) {
    const host = getHost(state, listing.hostId);
    const shouldAdjust = listing.availabilityStrategy === 'underbooked' || state.currentDay % 3 === 0;
    if (shouldAdjust && !proposalExists(state, (proposal) => proposal.action.type === 'adjust_price' && proposal.action.listingId === listing.id)) {
      const newNightlyRate = Math.max(120, Math.round(listing.nightlyRate * 0.92));
      createProposal(state, {
        humanRole: 'host',
        humanId: host.id,
        humanName: host.name,
        agentName: 'Host Agent',
        title: `Adjust nightly price for ${listing.title}`,
        description: `Occupancy looks soft. Lower the nightly rate from $${listing.nightlyRate} to $${newNightlyRate}?`,
        action: { type: 'adjust_price', listingId: listing.id, newNightlyRate },
        loopTrace: buildLoopTrace({
          actor: 'Host Agent',
          monitor: 'Watched listing occupancy, pace, and rate competitiveness.',
          detect: 'Detected underbooking pressure on upcoming dates.',
          propose: 'Proposed a dynamic pricing adjustment for host approval.',
        }),
      });
    }
  }
}

export function runAdminAgentLoop(state) {
  for (const booking of state.bookings) {
    const admin = state.admins[0];
    if (booking.dispute?.status === 'open' && !proposalExists(state, (proposal) => proposal.bookingId === booking.id && proposal.humanRole === 'admin')) {
      const creditAmount = Math.min(state.rules.disputeCreditCap, booking.issue?.severity === 'high' ? 120 : 60);
      createProposal(state, {
        humanRole: 'admin',
        humanId: admin.id,
        humanName: admin.name,
        agentName: 'Admin Agent',
        bookingId: booking.id,
        title: `Mediate dispute for ${getListing(state, booking.listingId).title}`,
        description: `Issue summary: ${booking.issue?.summary}. Apply a neutral mediation credit of $${creditAmount}?`,
        action: {
          type: 'admin_resolution',
          creditAmount,
          resolution: `Admin issued a $${creditAmount} marketplace credit after reviewing the unresolved stay issue.`,
        },
        loopTrace: buildLoopTrace({
          actor: 'Admin Agent',
          monitor: 'Watched open disputes, failed negotiations, and marketplace rules.',
          detect: 'Detected a dispute that guest and host agents could not close.',
          propose: 'Proposed a rule-based mediation outcome for admin approval.',
        }),
      });
    }
  }
}

export function runAllAgentLoops(state) {
  runGuestAgentLoop(state);
  runHostAgentLoop(state);
  runAdminAgentLoop(state);
  return state;
}

export function approveProposal(state, proposalId) {
  const proposal = state.proposals.find((candidate) => candidate.id === proposalId);
  if (!proposal || proposal.status !== 'pending') return state;
  proposal.status = 'approved';
  proposal.decidedDay = state.currentDay;

  switch (proposal.action.type) {
    case 'create_inquiry':
      approveGuestBookingProposal(state, proposal);
      break;
    case 'counter_inquiry':
      approveHostCounterProposal(state, proposal);
      break;
    case 'accept_counter':
      approveGuestCounterAcceptance(state, proposal);
      break;
    case 'check_in_guest':
      approveCheckIn(state, proposal);
      break;
    case 'offer_issue_resolution':
      approveIssueResolution(state, proposal);
      break;
    case 'escalate_dispute':
      approveDisputeEscalation(state, proposal);
      break;
    case 'admin_resolution':
      approveAdminResolution(state, proposal);
      break;
    case 'check_out_guest':
      approveCheckout(state, proposal);
      break;
    case 'submit_review':
      approveReview(state, proposal);
      break;
    case 'schedule_turnover':
      approveTurnover(state, proposal);
      break;
    case 'adjust_price':
      approvePriceAdjustment(state, proposal);
      break;
    default:
      logActivity(state, 'proposal_approved', `Approved proposal ${proposal.title}.`, { proposalId });
      break;
  }

  return state;
}

export function rejectProposal(state, proposalId) {
  const proposal = state.proposals.find((candidate) => candidate.id === proposalId);
  if (!proposal || proposal.status !== 'pending') return state;
  proposal.status = 'rejected';
  proposal.decidedDay = state.currentDay;

  switch (proposal.action.type) {
    case 'offer_issue_resolution':
      rejectIssueResolution(state, proposal);
      break;
    default:
      genericReject(state, proposal);
      break;
  }

  return state;
}

export function serializeState(state) {
  return JSON.stringify(state);
}

export function hydrateState(serialized) {
  return typeof serialized === 'string' ? JSON.parse(serialized) : deepClone(serialized);
}

export function getDayLabel(state, day = state.currentDay) {
  return addDays(state.baseDate, day - 1);
}

export function getProposalQueue(state, humanRole) {
  return state.proposals.filter((proposal) => proposal.status === 'pending' && (!humanRole || proposal.humanRole === humanRole));
}

export function getVisibleThread(state, bookingId) {
  const booking = getBooking(state, bookingId);
  return booking?.thread || [];
}

export function summarizeBooking(state, booking) {
  const listing = getListing(state, booking.listingId);
  const guest = getGuest(state, booking.guestId);
  return {
    ...booking,
    listingTitle: listing?.title,
    guestName: guest?.name,
    hostName: getHost(state, booking.hostId)?.name,
    totalValue: nightlyTotal(booking),
  };
}
