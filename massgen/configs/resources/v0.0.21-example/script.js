/* Theme and interaction script - vanilla JS */
(function () {
  const root = document.documentElement;
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)');
  const STORAGE_KEY = 'mg-theme';

  function getStoredTheme() { try { return localStorage.getItem(STORAGE_KEY); } catch { return null; } }
  function setStoredTheme(v) { try { localStorage.setItem(STORAGE_KEY, v); } catch {} }

  function applyTheme(theme) {
    if (theme === 'light' || theme === 'dark') {
      root.setAttribute('data-theme', theme);
    } else {
      root.setAttribute('data-theme', prefersDark.matches ? 'dark' : 'light');
    }
  }

  // Initialize theme: respect user pref or system
  const initial = getStoredTheme();
  applyTheme(initial || 'auto');

  // Respond to OS change if user hasn't explicitly chosen
  prefersDark.addEventListener('change', () => {
    if (!getStoredTheme()) applyTheme('auto');
  });

  // Toggle button
  const toggleBtn = document.getElementById('themeToggle');
  toggleBtn?.addEventListener('click', () => {
    const current = root.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    // micro interaction ripple
    ripple(toggleBtn);
    root.style.transition = 'background 500ms cubic-bezier(.2,.8,.2,1), color 200ms cubic-bezier(.2,.8,.2,1)';
    requestAnimationFrame(() => applyTheme(next));
    setStoredTheme(next);
    setTimeout(() => (root.style.transition = ''), 600);
  });

  function ripple(el) {
    const r = document.createElement('span');
    r.className = 'ripple';
    const rect = el.getBoundingClientRect();
    r.style.left = rect.width / 2 + 'px';
    r.style.top = rect.height / 2 + 'px';
    el.appendChild(r);
    setTimeout(() => r.remove(), 450);
  }

  // Live search + topic filter
  const searchInput = document.getElementById('searchInput');
  const chips = Array.from(document.querySelectorAll('.chip'));
  const posts = Array.from(document.querySelectorAll('.card'));
  const resultsMeta = document.getElementById('resultsMeta');

  let activeTopic = 'all';
  let query = '';

  function updateFilter() {
    const q = query.trim().toLowerCase();
    let visible = 0;

    posts.forEach((card) => {
      const topic = card.getAttribute('data-topic')?.toLowerCase() || '';
      const title = card.querySelector('.card-title')?.textContent?.toLowerCase() || '';
      const body = card.querySelector('.card-body')?.textContent?.toLowerCase() || '';
      const matchesTopic = activeTopic === 'all' || topic === activeTopic.toLowerCase();
      const matchesQuery = !q || title.includes(q) || body.includes(q);
      const show = matchesTopic && matchesQuery;
      const isHidden = card.classList.contains('hide');

      if (show) {
        visible++;
        card.style.display = '';
        // play in-animation if it was hidden
        if (isHidden) card.classList.remove('hide');
      } else {
        // smooth out by playing out-animation then hide by height collapse
        if (!isHidden) {
          card.classList.add('hide');
          setTimeout(() => { card.style.display = 'none'; }, 250);
        }
      }
    });

    const total = posts.length;
    const topicText = activeTopic === 'all' ? 'All topics' : `Topic: ${capitalize(activeTopic)}`;
    const qText = q ? `, Query: "${q}"` : '';
    resultsMeta.textContent = `${visible} of ${total} visible — ${topicText}${qText}`;
  }

  function capitalize(s){ return s.charAt(0).toUpperCase() + s.slice(1); }

  searchInput?.addEventListener('input', (e) => {
    query = e.target.value;
    updateFilter();
  });

  chips.forEach(ch => ch.addEventListener('click', () => {
    chips.forEach(c => c.classList.remove('is-active'));
    ch.classList.add('is-active');
    activeTopic = ch.dataset.topic || 'all';
    updateFilter();
  }));

  // Reading time estimate (220 wpm heuristic)
  const WPM = 220;
  posts.forEach((card, idx) => {
    const bodyEl = card.querySelector('[data-body-ref]')?.closest('.card')?.querySelector('.card-body') || card.querySelector('.card-body');
    const bodyText = bodyEl?.textContent || '';
    const words = bodyText.trim().split(/\s+/).filter(Boolean).length;
    const mins = Math.max(1, Math.round(words / WPM));
    const rt = card.querySelector('.reading-time');
    if (rt) rt.textContent = `${mins} min read`;

    // set stable id for reactions
    const id = card.querySelector('.card-title')?.textContent?.trim() || `post-${idx}`;
    card.dataset.postId = id;
  });

  // Reactions per post (localStorage persistence)
  const REACT_KEY = 'mg-reactions-v1';
  function loadReactions(){ try { return JSON.parse(localStorage.getItem(REACT_KEY)) || {}; } catch { return {}; } }
  function saveReactions(obj){ try { localStorage.setItem(REACT_KEY, JSON.stringify(obj)); } catch {} }
  const reactions = loadReactions();

  posts.forEach((card, idx) => {
    const id = card.dataset.postId || `post-${idx}`;
    const clapBtn = card.querySelector('.react[data-type="clap"]');
    const heartBtn = card.querySelector('.react[data-type="heart"]');

    const stored = reactions[id] || { clap: 0, heart: 0 };
    setCount(clapBtn, stored.clap);
    setCount(heartBtn, stored.heart);

    clapBtn?.addEventListener('click', () => {
      animateCount(clapBtn);
      const n = (reactions[id]?.clap || 0) + 1;
      updateReaction(id, 'clap', n);
      setCount(clapBtn, n);
    });

    heartBtn?.addEventListener('click', () => {
      animateCount(heartBtn);
      const n = (reactions[id]?.heart || 0) + 1;
      updateReaction(id, 'heart', n);
      setCount(heartBtn, n);
    });
  });

  function setCount(btn, n){ if (!btn) return; const c = btn.querySelector('.count'); if (c) c.textContent = n; }
  function updateReaction(id, type, n){ reactions[id] = { ...(reactions[id]||{}), [type]: n }; saveReactions(reactions); }

  function animateCount(btn){
    if (!btn) return;
    btn.animate([
      { transform: 'translateY(0) scale(1)' },
      { transform: 'translateY(-2px) scale(1.08)' },
      { transform: 'translateY(0) scale(1)' }
    ], { duration: 220, easing: 'cubic-bezier(.2,.8,.2,1)' });
  }

  // Share button (Web Share API with clipboard fallback)
  posts.forEach((card) => {
    const share = card.querySelector('.share');
    share?.addEventListener('click', async () => {
      const title = card.querySelector('.card-title')?.textContent?.trim() || 'Check this out';
      const url = location.href.split('#')[0];
      const text = `${title} — ${url}`;
      try {
        if (navigator.share) {
          await navigator.share({ title, text, url });
        } else if (navigator.clipboard) {
          await navigator.clipboard.writeText(text);
          toast('Link copied to clipboard');
        } else {
          // legacy fallback
          const ta = document.createElement('textarea');
          ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
          toast('Link copied');
        }
      } catch (e) {
        toast('Share cancelled');
      }
    });
  });

  // Tiny toast utility
  function toast(msg){
    let t = document.createElement('div');
    t.className = 'toast';
    t.textContent = msg;
    document.body.appendChild(t);
    requestAnimationFrame(() => t.classList.add('show'));
    setTimeout(() => { t.classList.remove('show'); setTimeout(()=>t.remove(), 300); }, 1800);
  }

  // Results meta initial
  updateFilter();
})();
