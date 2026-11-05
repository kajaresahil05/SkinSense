/**
 * SkinSense Toast Notification Utility
 */
window.Toast = {
  show: function (message, type = 'info', title = '', duration = 4000) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
      container.style.zIndex = '9999';
      document.body.appendChild(container);
    }

    const icons = {
      success: 'fa-circle-check text-emerald',
      error: 'fa-triangle-exclamation text-rose',
      danger: 'fa-triangle-exclamation text-rose',
      warning: 'fa-circle-exclamation text-amber',
      info: 'fa-circle-info text-teal'
    };

    const titleDefault = {
      success: 'Success',
      error: 'Error',
      danger: 'Error',
      warning: 'Warning',
      info: 'Notification'
    };

    const toastId = 'toast-' + Date.now();
    const iconClass = icons[type] || icons.info;
    const toastTitle = title || titleDefault[type] || 'SkinSense';

    const toastHtml = `
      <div id="${toastId}" class="toast align-items-center show shadow-lg" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="toast-header">
          <i class="fa-solid ${iconClass} me-2 fs-5"></i>
          <strong class="me-auto fs-6 text-main">${toastTitle}</strong>
          <small class="text-muted">Just now</small>
          <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
        <div class="toast-body text-secondary fs-7">
          ${message}
        </div>
      </div>
    `;

    container.insertAdjacentHTML('beforeend', toastHtml);
    const toastEl = document.getElementById(toastId);

    if (window.bootstrap && window.bootstrap.Toast) {
      const bsToast = new window.bootstrap.Toast(toastEl, { delay: duration });
      bsToast.show();
      toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
    } else {
      setTimeout(() => {
        toastEl.remove();
      }, duration);
    }
  },

  success: function (message, title) {
    this.show(message, 'success', title);
  },

  error: function (message, title) {
    this.show(message, 'error', title);
  },

  warning: function (message, title) {
    this.show(message, 'warning', title);
  },

  info: function (message, title) {
    this.show(message, 'info', title);
  }
};
