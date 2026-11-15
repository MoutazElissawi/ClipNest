/* ClipNest site behaviour. Every working fragment runs without the motion libraries; GSAP, ScrollTrigger and
   Lenis only add the motion layer, and nothing starts hidden unless this script is running. */
(() => {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fine = window.matchMedia('(pointer: fine)').matches;
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const pad = (n) => String(n).padStart(2, '0');
  const stamp = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}-${pad(d.getMinutes())}-${pad(d.getSeconds())}`;
  const safeName = (s) => s.replace(/[\\/:*?"<>|]+/g, '').trim();

  /* Hero: the instant replay, working. S or the key saves the last 90 seconds. */
  const replay = $('.replay');
  if (replay) {
    const video = $('.replay__video', replay);
    const pause = $('.replay__pause', replay);
    const key = $('.keycap', replay);
    const toast = $('.toast', replay);
    const fill = $('.buffer__fill', replay);
    const list = $('.saved', replay);
    let hideTimer;
    if (reduce) { video.removeAttribute('autoplay'); video.pause(); pause.classList.add('is-paused'); }
    pause.addEventListener('click', () => {
      if (video.paused) { video.play(); pause.classList.remove('is-paused'); pause.setAttribute('aria-label', 'Pause the gameplay video'); }
      else { video.pause(); pause.classList.add('is-paused'); pause.setAttribute('aria-label', 'Play the gameplay video'); }
    });
    const fillToast = () => {
      if (toast.childElementCount) return;
      [['toast__brand', 'CLIPNEST'], ['toast__title', 'Clip saved'], ['toast__detail', 'Your highlight is ready to edit']].forEach(([cls, text]) => {
        const s = document.createElement('span');
        s.className = cls;
        s.textContent = text;
        toast.append(s);
      });
    };
    const save = () => {
      fillToast();
      key.classList.add('is-pressed');
      setTimeout(() => key.classList.remove('is-pressed'), 160);
      toast.classList.remove('is-shown');
      void toast.offsetWidth;
      toast.classList.add('is-shown');
      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => toast.classList.remove('is-shown'), 3200);
      const row = document.createElement('li');
      const name = document.createElement('span');
      const len = document.createElement('span');
      name.textContent = `Valorant_${stamp(new Date())}.mkv`;
      len.textContent = '01:30';
      row.append(name, len);
      list.prepend(row);
      while (list.children.length > 3) list.lastElementChild.remove();
      if (!reduce) {
        fill.animate([{ transform: 'scaleX(0.02)' }, { transform: 'scaleX(1)' }], { duration: 2400, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' });
        if (window.gsap) gsap.from(row, { y: -8, opacity: 0, duration: 0.5, ease: 'expo.out' });
      }
    };
    key.addEventListener('click', save);
    document.addEventListener('keydown', (e) => {
      if (e.key.toLowerCase() !== 's' || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.target.closest('input, textarea, [contenteditable]')) return;
      save();
    });
  }

  /* The headline you can type: any game gets its own folder. */
  const input = $('#game-input');
  if (input) {
    const answer = $('.sorting__answer');
    const notes = {
      valorant: 'Hides from normal screen capture. Games only mode records it anyway.',
      'helldivers 2': 'Recorded with its game audio on a track of its own, apart from Discord and music.',
      'rocket league': 'Every replay from every match lands in this one folder.',
      fortnite: 'Its own folder from the first clip, with nothing to set up.',
    };
    const render = () => {
      const game = safeName(input.value) || 'Desktop';
      $('.path__game', answer).textContent = game;
      $('.file__name', answer).textContent = `${game}_${stamp(new Date())}.mkv`;
      $('.sorting__note', answer).textContent = notes[game.toLowerCase()] || 'A new folder appears the first time you save a clip from it.';
    };
    input.addEventListener('input', render);
    $$('.sorting__examples button').forEach((b) => b.addEventListener('click', () => { input.value = b.dataset.game; render(); input.focus(); }));
    render();
  }

  /* Editor fragments: the real Desktop waveform, a mute that toggles, track checkboxes, export format. */
  const peaks = [0.202,0.193,0.215,0.15,0.168,0.21,0.174,0.151,0.152,0.216,0.347,0.226,0.222,0.18,0.204,0.145,0.165,0.17,0.17,0.174,0.154,0.208,0.212,0.185,0.182,0.211,0.328,0.497,0.319,0.333,0.455,0.383,0.378,0.39,0.276,0.247,0.206,0.236,0.286,0.163,0.2,0.231,0.183,0.237,0.433,0.339,0.268,0.253,0.22,0.158,0.151,0.148,0.139,0.337,0.135,0.134,0.109,0.123,0.228,0.458,0.2,0.147,0.148,0.147,0.15,0.173,0.137,0.132,0.15,0.153,0.2,0.216,0.124,0.126,0.203,0.127,0.121,0.233,0.198,0.133,0.118,0.123,0.136,0.135,0.097,0.109,0.138,0.108,0.089,0.111,0.1,0.134,0.085,0.09,0.097,0.119,0.104,0.084,0.086,0.058,0.077,0.062,0.078,0.089,0.073,0.061,0.067,0.099,0.111,0.064,0.252,0.202,0.148,0.199,0.235,0.176,0.121,0.128,0.127,0.121,0.239,0.144,0.177,0.118,0.088,0.084,0.072,0.328,0.267,0.374,0.405,0.384,0.36,0.43,0.339,0.31,0.334,0.334,0.225,0.662,1.0,0.189,0.117,0.071,0.05,0.162,0.203,0.514,0.251,0.354,0.469,0.243,0.186,0.163,0.167,0.185,0.142,0.168,0.136,0.123,0.262,0.267,0.156,0.193,0.183,0.137,0.34,0.288,0.147,0.161,0.193,0.214,0.235,0.316,0.225,0.204,0.132,0.162,0.202,0.2];
  const svg = $('.wave__svg');
  if (svg) {
    const ns = 'http://www.w3.org/2000/svg';
    const w = 360 / peaks.length;
    peaks.forEach((p, i) => {
      const h = Math.max(2, p * 60);
      const r = document.createElementNS(ns, 'rect');
      r.setAttribute('x', (i * w).toFixed(2));
      r.setAttribute('y', (32 - h / 2).toFixed(2));
      r.setAttribute('width', (w * 0.7).toFixed(2));
      r.setAttribute('height', h.toFixed(2));
      svg.append(r);
    });
    const muteBtn = $('.wave__bar .ui-button');
    const wave = $('.wave');
    muteBtn.addEventListener('click', () => {
      const on = muteBtn.getAttribute('aria-pressed') !== 'true';
      muteBtn.setAttribute('aria-pressed', String(on));
      muteBtn.textContent = on ? 'Mute' : 'Unmuted';
      wave.classList.toggle('is-unmuted', !on);
    });
  }
  $$('.tracks .ui-button').forEach((b, _, all) => b.addEventListener('click', () => {
    all.forEach((o) => { const on = o === b; o.setAttribute('aria-pressed', String(on)); o.textContent = on ? 'Listening' : 'Listen solo'; });
  }));
  $$('.formats [role="radio"]').forEach((b, _, all) => b.addEventListener('click', () => {
    all.forEach((o) => o.setAttribute('aria-checked', String(o === b)));
    $('.formats__note').textContent = b.textContent === 'Copy' ? 'Copy: no re-encode, done in seconds' : `${b.textContent}: encoded with your chosen encoder`;
  }));

  /* Gallery filter: direction aware, the tiles slide away from the tab you leave toward the one you pick. */
  const tabs = $('.tabs');
  if (tabs) {
    const buttons = $$('[role="tab"]', tabs);
    const fillTab = $('.tabs__fill', tabs);
    const tiles = $$('.tile');
    let current = 0;
    const place = (b) => { fillTab.style.width = `${b.offsetWidth}px`; fillTab.style.transform = `translateX(${b.offsetLeft}px)`; };
    const apply = (filter) => tiles.forEach((t) => { t.hidden = !(filter === 'all' || t.dataset.game === filter); });
    buttons.forEach((b, i) => b.addEventListener('click', () => {
      if (i === current) return;
      const dir = i > current ? 1 : -1;
      current = i;
      buttons.forEach((o) => o.setAttribute('aria-selected', String(o === b)));
      place(b);
      // The filter applies at once; the motion only decorates it, so a stalled animation never hides tiles.
      apply(b.dataset.filter);
      if (window.gsap && !reduce) {
        gsap.fromTo(tiles.filter((t) => !t.hidden), { x: 24 * dir, opacity: 0 },
          { x: 0, opacity: 1, duration: 0.5, ease: 'expo.out', stagger: 0.04, overwrite: true });
      }
    }));
    buttons.forEach((b, i, all) => b.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      const next = all[(i + (e.key === 'ArrowRight' ? 1 : all.length - 1)) % all.length];
      next.focus(); next.click();
    }));
    const settle = () => place(buttons[current]);
    window.addEventListener('resize', settle);
    if (document.fonts) document.fonts.ready.then(settle); else settle();
  }

  /* How it works: one slider drives the clause and the fragment. */
  const range = $('.steps__range');
  if (range) {
    const clauses = ['First, run the installer.', 'Then, point it at FFmpeg.', 'Now, press your hotkey.'];
    const texts = ['Run the installer', 'Point it at FFmpeg', 'Press your hotkey'];
    const now = $('.steps__now');
    const stages = $$('.stage');
    const names = $$('.steps__names li');
    let shown = 0;
    const set = (i) => {
      if (i === shown) return;
      shown = i;
      now.classList.add('is-swapping');
      setTimeout(() => { now.textContent = clauses[i]; now.classList.remove('is-swapping'); }, reduce ? 0 : 200);
      stages.forEach((s, k) => s.classList.toggle('is-on', k === i));
      names.forEach((n, k) => n.classList.toggle('is-on', k === i));
      range.setAttribute('aria-valuetext', texts[i]);
    };
    range.addEventListener('input', () => set(Number(range.value)));
    names.forEach((n, k) => { n.style.cursor = 'pointer'; n.addEventListener('click', () => { range.value = k; set(k); }); });
  }

  /* FAQ: on wide screens one large answer pane follows hover, click and focus; on phones answers open inline. */
  const faq = $('.faq');
  if (faq) {
    const qs = $$('.faq__list button', faq);
    const pane = $('.faq__shown', faq);
    const wide = window.matchMedia('(min-width: 900px)');
    const select = (btn) => {
      qs.forEach((q) => {
        const on = q === btn;
        q.setAttribute('aria-expanded', String(on));
        document.getElementById(q.getAttribute('aria-controls')).hidden = !on;
      });
      if (wide.matches) {
        pane.classList.add('is-swapping');
        setTimeout(() => { pane.textContent = document.getElementById(btn.getAttribute('aria-controls')).textContent; pane.classList.remove('is-swapping'); }, reduce ? 0 : 150);
      }
    };
    const mode = () => faq.classList.toggle('faq--pane', wide.matches);
    wide.addEventListener('change', mode);
    mode();
    qs.forEach((q) => {
      q.addEventListener('click', () => select(q));
      q.addEventListener('focus', () => { if (wide.matches) select(q); });
      q.addEventListener('mouseenter', () => { if (wide.matches) select(q); });
    });
  }

  /* The close: the picture changes slowly, like light shifting in a room. */
  const photos = $$('.close__side--photo img');
  if (photos.length > 1 && !reduce) {
    let k = 0;
    setInterval(() => {
      if (document.hidden) return;
      photos[k].classList.remove('is-on');
      k = (k + 1) % photos.length;
      photos[k].classList.add('is-on');
    }, 5600);
  }

  /* The bar shows where you are. */
  const links = $$('.bar__links a');
  if ('IntersectionObserver' in window && links.length) {
    const map = new Map(links.map((a) => [document.querySelector(a.getAttribute('href')), a]));
    const io = new IntersectionObserver((entries) => entries.forEach((en) => {
      const a = map.get(en.target);
      if (a && en.isIntersecting) { links.forEach((l) => l.removeAttribute('aria-current')); a.setAttribute('aria-current', 'true'); }
    }), { rootMargin: '-40% 0px -55% 0px' });
    map.forEach((_, sec) => { if (sec) io.observe(sec); });
  }

  /* Motion layer: Lenis smooth scroll, section part entrances, the tagline words, the magnet buttons. */
  const words = $('[data-words]');
  if (words) {
    const parts = words.textContent.trim().split(/\s+/);
    words.textContent = '';
    parts.forEach((w, i) => {
      const s = document.createElement('span');
      s.className = 'w';
      s.textContent = w;
      words.append(s, i < parts.length - 1 ? ' ' : '');
    });
  }
  const lightAll = () => $$('.why__lead .w').forEach((w) => w.classList.add('is-lit'));
  window.addEventListener('load', () => {
    if (reduce || !window.gsap || !window.ScrollTrigger) { lightAll(); return; }
    gsap.registerPlugin(ScrollTrigger);
    if (window.Lenis) {
      const lenis = new Lenis({ lerp: 0.12, smoothWheel: true });
      lenis.on('scroll', ScrollTrigger.update);
      gsap.ticker.add((t) => lenis.raf(t * 1000));
      gsap.ticker.lagSmoothing(0);
      $$('a[href^="#"]').forEach((a) => a.addEventListener('click', (e) => {
        const target = document.querySelector(a.getAttribute('href'));
        if (!target) return;
        e.preventDefault();
        lenis.scrollTo(target, { offset: -24 });
        target.setAttribute('tabindex', '-1');
        target.focus({ preventScroll: true });
      }));
    }
    $$('[data-reveal]').forEach((block) => {
      const parts = block.children.length > 1 ? [...block.children] : [block];
      gsap.from(parts, {
        y: 24, opacity: 0, duration: 0.7, ease: 'expo.out', stagger: 0.07,
        scrollTrigger: { trigger: block, start: 'top 88%', once: true },
      });
    });
    $$('.why__lead .w').forEach((w) => {
      ScrollTrigger.create({ trigger: w, start: 'top 72%', once: true, onEnter: () => w.classList.add('is-lit') });
    });
    gsap.fromTo('.replay__video', { scale: 1.06 }, { scale: 1, ease: 'none', scrollTrigger: { trigger: '.replay', start: 'top bottom', end: 'bottom top', scrub: true } });
    if (fine) {
      $$('.magnet').forEach((m) => {
        const x = gsap.quickTo(m, 'x', { duration: 0.5, ease: 'expo.out' });
        const y = gsap.quickTo(m, 'y', { duration: 0.5, ease: 'expo.out' });
        m.addEventListener('pointermove', (e) => {
          const r = m.getBoundingClientRect();
          x((e.clientX - r.left - r.width / 2) * 0.18);
          y((e.clientY - r.top - r.height / 2) * 0.28);
        });
        m.addEventListener('pointerleave', () => { x(0); y(0); });
      });
    }
  });
})();
