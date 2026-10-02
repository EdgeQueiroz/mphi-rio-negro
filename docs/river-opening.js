/* Decorative footage only; no connection with hydrological data or forecasts. */
(() => {
  'use strict';
  const hero = document.getElementById('riverOpening');
  const video = document.getElementById('riverVideo');
  const toggle = document.getElementById('riverMotionToggle');
  const label = document.getElementById('riverMotionLabel');
  if (!hero || !video || !toggle || !label) return;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const connection = navigator.connection;
  let inView = true;
  let manuallyPaused = false;
  let failed = false;
  const allowMotion = () => !reducedMotion.matches && !connection?.saveData &&
    !['slow-2g', '2g', '3g'].includes(connection?.effectiveType);
  const updateControl = () => {
    toggle.setAttribute('aria-pressed', String(manuallyPaused));
    toggle.setAttribute('aria-label', manuallyPaused ? 'Reproduzir animação do rio' : 'Pausar animação do rio');
    label.textContent = manuallyPaused ? 'Reproduzir rio' : 'Pausar rio';
    toggle.firstElementChild.textContent = manuallyPaused ? '▷' : 'Ⅱ';
  };
  const synchronize = () => {
    if (!allowMotion() || failed) {
      video.pause();
      hero.classList.remove('river-playing');
      toggle.hidden = true;
      if (video.hasAttribute('src')) {
        video.removeAttribute('src');
        video.load();
      }
      return;
    }
    if (!video.hasAttribute('src')) {
      video.src = window.matchMedia('(max-width: 780px)').matches ? video.dataset.mobileSrc : video.dataset.desktopSrc;
      video.muted = true;
    }
    if (document.hidden || !inView || manuallyPaused) {
      video.pause();
      return;
    }
    video.play().catch(() => {
      // Autoplay policies retain the poster and let the visitor start motion.
      manuallyPaused = true;
      toggle.hidden = false;
      updateControl();
    });
  };
  video.addEventListener('playing', () => {
    hero.classList.add('river-playing');
    toggle.hidden = false;
    updateControl();
  });
  video.addEventListener('error', () => { failed = true; synchronize(); });
  toggle.addEventListener('click', () => {
    manuallyPaused = !manuallyPaused;
    updateControl();
    synchronize();
  });
  reducedMotion.addEventListener('change', synchronize);
  connection?.addEventListener('change', synchronize);
  document.addEventListener('visibilitychange', synchronize);
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      synchronize();
    }, { threshold: 0 }).observe(hero);
  }
  synchronize();
})();
