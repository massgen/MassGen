import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

class FakeElement {
  constructor() {
    this.innerHTML = '';
    this.listeners = new Map();
  }

  addEventListener(type, handler) {
    this.listeners.set(type, handler);
  }

  dispatch(type, event) {
    const handler = this.listeners.get(type);
    if (handler) handler(event);
  }
}

function createStorage() {
  const store = new Map();
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
    removeItem(key) {
      store.delete(key);
    },
    dump(key) {
      return store.get(key);
    },
  };
}

test('browser UI renders and approves a booking inquiry through the click layer', async () => {
  const appEl = new FakeElement();
  const localStorage = createStorage();

  global.window = {
    localStorage,
    setInterval() {
      return 1;
    },
  };

  global.document = {
    querySelector(selector) {
      if (selector === '#app') return appEl;
      return null;
    },
  };

  const moduleUrl = `${pathToFileURL(path.resolve('deliverable/app.mjs')).href}?ui_smoke=${Date.now()}`;
  await import(moduleUrl);

  assert.match(appEl.innerHTML, /StayFlow Agents/);
  assert.match(appEl.innerHTML, /Guest approvals/);

  const initialState = JSON.parse(localStorage.dump('stayflow-rental-marketplace-v1'));
  const firstGuestProposal = initialState.proposals.find(
    (proposal) => proposal.status === 'pending' && proposal.humanRole === 'guest',
  );
  assert.ok(firstGuestProposal, 'expected a guest proposal in local storage');

  appEl.dispatch('click', {
    target: {
      closest(selector) {
        if (selector === 'button[data-action]') {
          return { dataset: { action: 'approve-proposal', id: firstGuestProposal.id } };
        }
        return null;
      },
    },
  });

  const afterApproval = JSON.parse(localStorage.dump('stayflow-rental-marketplace-v1'));
  assert.equal(afterApproval.bookings.length, 1);
  assert.equal(afterApproval.bookings[0].stage, 'inquiry');
  assert.match(appEl.innerHTML, /Bookings, negotiation threads, and stay monitoring/);

  delete global.window;
  delete global.document;
});
