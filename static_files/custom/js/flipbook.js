/**
 * LoanMasta Flipbook — a small, dependency-free magazine-style page turner.
 *
 * Markup expected:
 *   <div class="flipbook" id="{id}">
 *     <div class="fb-page"><img src="..."><span class="fb-page-num">1</span></div>
 *     ... one .fb-page per page, in reading order ...
 *   </div>
 *
 * Usage: LMFlipbook.init('myFlipbookId', { prevBtn, nextBtn, counterEl });
 */
(function (window) {
  'use strict';

  function init(flipbookId, opts) {
    opts = opts || {};
    var root = document.getElementById(flipbookId);
    if (!root) return null;

    var pages = Array.prototype.slice.call(root.querySelectorAll('.fb-page'));
    var total = pages.length;
    var flipped = pages.map(function () { return false; });
    var current = 0; // index of the top-most unflipped page
    var animating = false;

    function layout() {
      pages.forEach(function (el, i) {
        el.style.zIndex = flipped[i] ? i : (total - i);
      });
    }

    function updateControls() {
      if (opts.prevBtn) opts.prevBtn.disabled = current <= 0;
      if (opts.nextBtn) opts.nextBtn.disabled = current >= total - 1;
      if (opts.counterEl) opts.counterEl.textContent = (current + 1) + ' / ' + total;
    }

    function next() {
      if (animating || current >= total - 1) return;
      animating = true;
      var el = pages[current];
      el.style.zIndex = total + 10; // lift above the stack while it turns
      el.classList.add('flipped');

      var done = function () {
        el.removeEventListener('transitionend', done);
        flipped[current] = true;
        current += 1;
        layout();
        animating = false;
        updateControls();
      };
      el.addEventListener('transitionend', done, { once: true });
    }

    function prev() {
      if (animating || current <= 0) return;
      animating = true;
      current -= 1;
      var el = pages[current];
      flipped[current] = false;
      el.style.zIndex = total + 10; // lift above the stack while it turns back

      var done = function () {
        el.removeEventListener('transitionend', done);
        layout();
        animating = false;
        updateControls();
      };
      el.addEventListener('transitionend', done, { once: true });
      el.classList.remove('flipped');
    }

    // click the left third of the book to go back, the rest to go forward
    root.addEventListener('click', function (e) {
      var rect = root.getBoundingClientRect();
      var x = e.clientX - rect.left;
      if (x < rect.width * 0.32) {
        prev();
      } else {
        next();
      }
    });

    // keyboard support when the book has focus
    root.setAttribute('tabindex', '0');
    root.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight') next();
      if (e.key === 'ArrowLeft') prev();
    });

    // basic touch swipe support
    var touchStartX = null;
    root.addEventListener('touchstart', function (e) {
      touchStartX = e.changedTouches[0].clientX;
    }, { passive: true });
    root.addEventListener('touchend', function (e) {
      if (touchStartX === null) return;
      var dx = e.changedTouches[0].clientX - touchStartX;
      if (Math.abs(dx) > 40) {
        if (dx < 0) { next(); } else { prev(); }
      }
      touchStartX = null;
    }, { passive: true });

    if (opts.prevBtn) opts.prevBtn.addEventListener('click', function (e) { e.stopPropagation(); prev(); });
    if (opts.nextBtn) opts.nextBtn.addEventListener('click', function (e) { e.stopPropagation(); next(); });

    layout();
    updateControls();

    return { next: next, prev: prev };
  }

  window.LMFlipbook = { init: init };
})(window);
