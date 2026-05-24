// Auto-dismiss flash alerts after 5s
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    document.querySelectorAll('.alert.fade.show').forEach(a => {
      try { bootstrap.Alert.getOrCreateInstance(a).close(); } catch (e) {}
    });
  }, 5000);

  setupThemeToggle();
  setupPageTransitionLoader();
  setupCursorGlow();
});

function setupThemeToggle() {
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  const root = document.documentElement;

  function syncIcons(theme) {
    btn.querySelectorAll('[data-theme-icon]').forEach(icon => {
      icon.classList.toggle('d-none', icon.dataset.themeIcon !== theme);
    });
  }

  function applyTheme(theme) {
    root.setAttribute('data-theme', theme);
    root.setAttribute('data-bs-theme', theme);
    try { localStorage.setItem('theme', theme); } catch (e) {}
    syncIcons(theme);
  }

  // Sync initial icon state with the theme set by the pre-paint inline script.
  syncIcons(root.getAttribute('data-theme') || 'light');

  btn.addEventListener('click', () => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    applyTheme(next);
  });
}

function setupPageTransitionLoader() {
  const loader = ensurePageLoaderElement();
  const startUrl = new URL(window.location.href);
  let safetyTimer = null;

  function showPageLoader() {
    if (loader.classList.contains('is-visible')) return;
    loader.classList.add('is-visible');
    document.body.classList.add('is-page-transitioning');

    if (safetyTimer) clearTimeout(safetyTimer);
    safetyTimer = setTimeout(() => {
      // If navigation was cancelled or blocked, avoid a stuck overlay.
      hidePageLoader();
    }, 1800);
  }

  function hidePageLoader() {
    loader.classList.remove('is-visible');
    document.body.classList.remove('is-page-transitioning');
    if (safetyTimer) {
      clearTimeout(safetyTimer);
      safetyTimer = null;
    }
  }

  function isSamePageHashJump(url) {
    return (
      url.pathname === startUrl.pathname &&
      url.search === startUrl.search &&
      url.hash &&
      url.hash !== startUrl.hash
    );
  }

  function shouldShowForLink(link, event) {
    if (!link || event.defaultPrevented) return false;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return false;
    }
    if (link.dataset.noLoader !== undefined) return false;
    if (link.target && link.target !== '_self') return false;
    if (link.hasAttribute('download')) return false;

    const rawHref = (link.getAttribute('href') || '').trim();
    if (!rawHref || rawHref.startsWith('#') || rawHref.startsWith('javascript:')) {
      return false;
    }

    let url;
    try {
      url = new URL(link.href, window.location.href);
    } catch (e) {
      return false;
    }

    if (url.origin !== window.location.origin) return false;
    if (isSamePageHashJump(url)) return false;
    return true;
  }

  function shouldShowForForm(form) {
    if (!form || form.dataset.noLoader !== undefined) return false;
    if (form.target && form.target !== '_self') return false;
    const method = (form.getAttribute('method') || 'get').toLowerCase();
    return method !== 'dialog';
  }

  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!shouldShowForLink(link, event)) return;
    showPageLoader();
  });

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (!shouldShowForForm(form)) return;
    queueMicrotask(() => {
      if (!event.defaultPrevented) showPageLoader();
    });
  });

  // Programmatic navigations / refreshes.
  window.addEventListener('beforeunload', showPageLoader);
  // Back-forward cache restores.
  window.addEventListener('pageshow', hidePageLoader);
  // Initial render safety.
  hidePageLoader();
}

function ensurePageLoaderElement() {
  let loader = document.getElementById('page-transition-loader');
  if (loader) return loader;

  loader = document.createElement('div');
  loader.id = 'page-transition-loader';
  loader.className = 'page-transition-loader';
  loader.setAttribute('aria-hidden', 'true');
  loader.innerHTML = `
    <div class="page-transition-loader__panel" role="status" aria-live="polite">
      <span class="spinner-border page-transition-loader__spinner" aria-hidden="true"></span>
      <span class="page-transition-loader__text">页面加载中...</span>
    </div>
  `;
  document.body.appendChild(loader);
  return loader;
}

function setupCursorGlow() {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const supportsFinePointer = window.matchMedia('(pointer: fine)').matches;
  if (prefersReducedMotion || !supportsFinePointer) return;

  const glow = ensureCursorGlowElement();
  const interactiveSelector = 'a, button, .btn, .nav-link, .list-group-item-action, input, select, textarea, [role="button"]';

  let targetX = window.innerWidth / 2;
  let targetY = window.innerHeight / 2;
  let currentX = targetX;
  let currentY = targetY;
  let rafId = 0;
  const ease = 0.2;

  function updateFrame() {
    currentX += (targetX - currentX) * ease;
    currentY += (targetY - currentY) * ease;
    glow.style.transform = `translate3d(${currentX}px, ${currentY}px, 0) translate(-50%, -50%)`;

    if (Math.abs(targetX - currentX) > 0.08 || Math.abs(targetY - currentY) > 0.08) {
      rafId = window.requestAnimationFrame(updateFrame);
    } else {
      rafId = 0;
    }
  }

  function queueFrame() {
    if (!rafId) rafId = window.requestAnimationFrame(updateFrame);
  }

  document.addEventListener('mousemove', event => {
    targetX = event.clientX;
    targetY = event.clientY;
    if (!glow.classList.contains('is-visible')) {
      glow.classList.add('is-visible');
    }
    queueFrame();
  });

  document.addEventListener('mouseleave', () => {
    glow.classList.remove('is-visible');
    glow.classList.remove('is-hovering');
    glow.classList.remove('is-pressed');
  });

  document.addEventListener('mousedown', () => {
    glow.classList.add('is-pressed');
  });

  document.addEventListener('mouseup', () => {
    glow.classList.remove('is-pressed');
  });

  document.addEventListener('mouseover', event => {
    if (event.target.closest(interactiveSelector)) {
      glow.classList.add('is-hovering');
    }
  });

  document.addEventListener('mouseout', event => {
    const next = event.relatedTarget;
    if (next && next.closest && next.closest(interactiveSelector)) return;
    glow.classList.remove('is-hovering');
  });

  window.addEventListener('blur', () => {
    glow.classList.remove('is-visible');
    glow.classList.remove('is-hovering');
    glow.classList.remove('is-pressed');
  });
}

function ensureCursorGlowElement() {
  let glow = document.getElementById('cursor-glow');
  if (glow) return glow;

  glow = document.createElement('div');
  glow.id = 'cursor-glow';
  glow.className = 'cursor-glow';
  glow.setAttribute('aria-hidden', 'true');
  document.body.appendChild(glow);
  return glow;
}
