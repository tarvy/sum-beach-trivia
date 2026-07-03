// Shared house-styled UI helpers — plain <script src>, no build step.
// Use sbtConfirm() instead of the native confirm()/alert(): those are ugly
// browser chrome and clash with the Gumroad house style. Returns a Promise<bool>.
(function () {
  function sbtConfirm(message, opts) {
    opts = opts || {};
    const okText = opts.okText || 'Confirm';
    const cancelText = opts.cancelText || 'Cancel';
    const danger = !!opts.danger;
    const title = opts.title || '';
    return new Promise(function (resolve) {
      const back = document.createElement('div');
      back.className = 'modal-backdrop';
      back.innerHTML =
        '<div class="modal-card" role="dialog" aria-modal="true">' +
          (title ? '<h3 class="modal-title mb-sm"></h3>' : '') +
          '<p class="modal-msg"></p>' +
          '<div class="cluster mt-md" style="justify-content: flex-end;">' +
            '<button class="btn btn--secondary" data-act="cancel"></button>' +
            '<button class="btn ' + (danger ? 'btn--danger' : 'btn--primary') + '" data-act="ok"></button>' +
          '</div>' +
        '</div>';
      // textContent everywhere — never inject caller strings as HTML
      if (title) back.querySelector('.modal-title').textContent = title;
      back.querySelector('.modal-msg').textContent = message;
      back.querySelector('[data-act="cancel"]').textContent = cancelText;
      back.querySelector('[data-act="ok"]').textContent = okText;

      function close(val) {
        back.remove();
        document.removeEventListener('keydown', onKey);
        resolve(val);
      }
      function onKey(e) {
        if (e.key === 'Escape') close(false);
        else if (e.key === 'Enter') close(true);
      }
      back.addEventListener('click', function (e) {
        if (e.target === back) return close(false);  // click the backdrop = cancel
        const act = e.target.closest('[data-act]');
        if (act) close(act.dataset.act === 'ok');
      });
      document.addEventListener('keydown', onKey);
      document.body.appendChild(back);
      back.querySelector('[data-act="ok"]').focus();
    });
  }
  window.sbtConfirm = sbtConfirm;
})();
