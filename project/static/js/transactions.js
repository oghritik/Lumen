/**
 * Transaction Page — Center-Focus Scroll Animation
 *
 * Detects how far each card is from the scroll container's vertical center
 * and dynamically applies scale, opacity, rotateX, and blur via inline
 * transforms.  Uses requestAnimationFrame to avoid layout thrashing.
 */
(function () {
  'use strict';

  /* ── Config ───────────────────────────────────────────────────────── */
  var CFG = {
    scaleMin:   0.85,   // farthest cards
    scaleMax:   1.0,    // center card
    opacityMin: 0.4,
    opacityMax: 1.0,
    rotateMax:  4,      // degrees — cards far from center
    blurMax:    2,      // px
    // Distance (px) at which a card is fully "far"
    falloff:    360
  };

  /* ── State ────────────────────────────────────────────────────────── */
  var container = null;
  var cards     = [];
  var ticking   = false;

  /* ── Month selector ───────────────────────────────────────────────── */
  var MONTHS = [
    'January','February','March','April','May','June',
    'July','August','September','October','November','December'
  ];
  var currentDate = new Date();

  window.changeMonth = function (dir) {
    currentDate.setMonth(currentDate.getMonth() + dir);
    var label = document.getElementById('monthLabel');
    if (label) {
      label.textContent = MONTHS[currentDate.getMonth()] + ' ' + currentDate.getFullYear();
    }
  };

  /* ── Helpers ──────────────────────────────────────────────────────── */
  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function clamp(v, lo, hi) {
    return v < lo ? lo : v > hi ? hi : v;
  }

  /* ── Core: compute & apply transforms ─────────────────────────────── */
  function applyFocus() {
    var rect      = container.getBoundingClientRect();
    var centerY   = rect.top + rect.height * 0.5;
    var closest   = null;
    var closestD  = Infinity;

    for (var i = 0; i < cards.length; i++) {
      var card  = cards[i];
      var cRect = card.getBoundingClientRect();
      var cardCenter = cRect.top + cRect.height * 0.5;
      var dist  = Math.abs(cardCenter - centerY);

      // Normalise: 0 = dead center, 1 = fully far
      var t = clamp(dist / CFG.falloff, 0, 1);

      var scale   = lerp(CFG.scaleMax,   CFG.scaleMin,   t);
      var opacity = lerp(CFG.opacityMax,  CFG.opacityMin, t);
      var rotate  = lerp(0, CFG.rotateMax, t);
      var blur    = lerp(0, CFG.blurMax,   t);

      // Direction of rotation: cards above center tilt downward, below tilt upward
      if (cardCenter < centerY) rotate = -rotate;

      card.style.transform = 'scale(' + scale.toFixed(4) + ') perspective(800px) rotateX(' + rotate.toFixed(2) + 'deg)';
      card.style.opacity   = opacity.toFixed(3);
      card.style.filter    = blur > 0.05 ? 'blur(' + blur.toFixed(2) + 'px)' : 'none';

      // Track closest card
      if (dist < closestD) {
        closestD = dist;
        closest  = card;
      }
    }

    // Toggle .is-focused class on nearest card
    for (var j = 0; j < cards.length; j++) {
      if (cards[j] === closest) {
        cards[j].classList.add('is-focused');
      } else {
        cards[j].classList.remove('is-focused');
      }
    }

    ticking = false;
  }

  function onScroll() {
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(applyFocus);
    }
  }

  /* ── Init ──────────────────────────────────────────────────────────── */
  function init() {
    container = document.getElementById('txnScrollContainer');
    if (!container) return;

    cards = Array.prototype.slice.call(
      container.querySelectorAll('.txn-card')
    );
    if (cards.length === 0) return;

    container.addEventListener('scroll', onScroll, { passive: true });

    // Also recompute on resize
    window.addEventListener('resize', onScroll, { passive: true });

    // Initial pass
    requestAnimationFrame(applyFocus);
  }

  // Run on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
