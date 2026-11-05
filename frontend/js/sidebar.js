/**
 * SkinSense Sidebar & Router Controller — Fixed v2.0
 * Fixes:
 *  - data-page attribute (was data-section)
 *  - page-${id} div IDs (was section-${id})
 *  - Exposes window.navigateTo globally
 *  - Proper auth-screen ↔ app-shell toggling
 *  - Section hooks for lazy data loading
 */
window.Navigation = {
  currentPage: null,

  init: function () {
    // Bind all sidebar nav buttons (use data-page attribute)
    document.querySelectorAll('.sidebar-nav-item[data-page]').forEach(btn => {
      btn.addEventListener('click', () => {
        const pageId = btn.getAttribute('data-page');
        if (pageId) this.navigateTo(pageId);
      });
    });

    // Sidebar user card click → profile
    const userCard = document.getElementById('sidebar-user-card');
    if (userCard) {
      userCard.addEventListener('click', () => this.navigateTo('profile'));
    }

    // Mobile sidebar toggle
    const mobileBtn = document.getElementById('mobile-sidebar-btn');
    const overlay   = document.getElementById('sidebar-overlay');
    const sidebar   = document.getElementById('app-sidebar');

    if (mobileBtn && sidebar) {
      mobileBtn.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('active');
      });
    }
    if (overlay && sidebar) {
      overlay.addEventListener('click', () => {
        sidebar.classList.remove('open');
        overlay.classList.remove('active');
      });
    }

    // Desktop sidebar collapse
    const desktopToggle = document.getElementById('desktop-sidebar-toggle');
    const appShell = document.getElementById('app-shell');
    if (desktopToggle && appShell) {
      desktopToggle.addEventListener('click', () => {
        appShell.classList.toggle('sidebar-collapsed');
      });
    }
  },

  /**
   * Navigate to a named page section.
   * @param {string} pageId - corresponds to <div id="page-${pageId}">
   */
  navigateTo: function (pageId) {
    // Hide all pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

    // Show target page
    const target = document.getElementById('page-' + pageId);
    if (!target) {
      console.warn('[Navigation] Page not found: page-' + pageId);
      return;
    }
    target.classList.add('active');
    this.currentPage = pageId;

    // Update active nav button
    document.querySelectorAll('.sidebar-nav-item').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-page') === pageId);
    });

    // Update header breadcrumb
    const navLabel = document.getElementById('nav-' + pageId)?.querySelector('[data-i18n]');
    const titleKey = navLabel?.dataset.i18n || 'nav_' + pageId.replace(/-/g, '_');
    const titleText = window.I18nModule ? window.I18nModule.t(titleKey) : pageId;
    const titleEl = document.getElementById('header-page-title');
    if (titleEl) titleEl.textContent = titleText;

    // Close mobile sidebar
    const sidebar = document.getElementById('app-sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');

    // Scroll to top
    const mainContent = document.querySelector('.main-content');
    if (mainContent) mainContent.scrollTop = 0;

    // Apply active language to page elements
    if (window.I18nModule) {
      window.I18nModule.applyLanguage(window.I18nModule.currentLang);
    }

    // Trigger lazy section loader
    if (window.SectionHooks && typeof window.SectionHooks[pageId] === 'function') {
      window.SectionHooks[pageId]();
    }
  },

  /**
   * Show the authenticated app shell; hide auth screen.
   * Called by Auth after successful login/register.
   */
  showAppShell: function (user, defaultPage) {
    const authScreen = document.getElementById('auth-screen');
    const appShell   = document.getElementById('app-shell');
    if (authScreen) authScreen.classList.add('d-none');
    if (appShell)   appShell.classList.remove('d-none');

    // Update sidebar user card
    this._updateSidebarUser(user);

    // Show/hide admin nav items
    this._applyRoleVisibility(user.role);

    // Navigate to appropriate default page
    const startPage = defaultPage || (user.role === 'admin' ? 'admin-dashboard' : 'dashboard');
    this.navigateTo(startPage);
  },

  /**
   * Show auth screen; hide app shell. Called on logout.
   */
  showAuthScreen: function () {
    const authScreen = document.getElementById('auth-screen');
    const appShell   = document.getElementById('app-shell');
    if (appShell)   appShell.classList.add('d-none');
    if (authScreen) authScreen.classList.remove('d-none');
    this.currentPage = null;
  },

  _updateSidebarUser: function (user) {
    const nameEl    = document.getElementById('sidebar-user-name');
    const roleEl    = document.getElementById('sidebar-user-role');
    const avatarEl  = document.getElementById('sidebar-avatar-initials');
    const headerEl  = document.getElementById('header-initials');

    if (!user) return;
    const initials = (user.full_name || 'U').split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
    if (nameEl)   nameEl.textContent  = user.full_name || 'Patient';
    if (roleEl)   roleEl.textContent  = user.role === 'admin' ? 'Administrator' : 'Patient';
    if (avatarEl) avatarEl.textContent = initials;
    if (headerEl) headerEl.textContent = initials;
  },

  _applyRoleVisibility: function (role) {
    const isAdmin = (role === 'admin');

    const patientSection = document.getElementById('patient-nav-section');
    const patientItems   = [
      document.getElementById('nav-dashboard'),
      document.getElementById('nav-scanner'),
      document.getElementById('nav-history'),
      document.getElementById('nav-tracking')
    ];

    const toolsSection = document.getElementById('tools-nav-section');
    const toolsItems   = [
      document.getElementById('nav-assistant'),
      document.getElementById('nav-education')
    ];

    const adminSection = document.getElementById('admin-nav-section');
    const adminItems   = document.querySelectorAll('.sidebar-nav-item[data-page^="admin-"]');

    if (patientSection) patientSection.classList.toggle('d-none', isAdmin);
    patientItems.forEach(item => { if (item) item.classList.toggle('d-none', isAdmin); });

    if (toolsSection) toolsSection.classList.toggle('d-none', isAdmin);
    toolsItems.forEach(item => { if (item) item.classList.toggle('d-none', isAdmin); });

    if (adminSection) adminSection.classList.toggle('d-none', !isAdmin);
    adminItems.forEach(item => item.classList.toggle('d-none', !isAdmin));
  }
};

// ── Global hook registry ──
window.SectionHooks = {};

// ── Expose navigateTo globally (used by onclick="navigateTo(...)" in HTML) ──
window.navigateTo = function (pageId) {
  Navigation.navigateTo(pageId);
};

// ── Also expose sendChatMessage globally (used by quick-prompt chips) ──
window.sendChatMessage = function (text) {
  const input = document.getElementById('chat-text-input');
  if (input) {
    input.value = text;
    const sendBtn = document.getElementById('chat-send-btn');
    if (sendBtn) sendBtn.click();
  }
};

document.addEventListener('DOMContentLoaded', () => {
  Navigation.init();
});
