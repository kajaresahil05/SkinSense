/**
 * SkinSense Authentication & Session Manager — Fixed v2.0
 * Fixes:
 *  - Calls Navigation.showAppShell() / showAuthScreen() to toggle screens
 *  - Corrects form field IDs: reg-confirm, reg-consent
 *  - handleForgotPassword calls real API endpoint
 *  - handleResetPassword calls real reset API endpoint
 *  - Admin sidebar items shown/hidden by role
 *  - evaluatePasswordStrength uses correct IDs
 */
window.Auth = {
  currentUser: null,

  init: function () {
    this.checkAuthStatus();
    this.bindEvents();
  },

  bindEvents: function () {
    // Auth tab pills
    document.querySelectorAll('.auth-tab-pill').forEach(btn => {
      btn.addEventListener('click', () => {
        const tabId = btn.getAttribute('data-tab');
        this._showAuthPane(tabId, btn);
      });
    });

    // Login form
    const loginForm = document.getElementById('login-form');
    if (loginForm) loginForm.addEventListener('submit', e => this.handleLogin(e));

    // Register form
    const regForm = document.getElementById('register-form');
    if (regForm) regForm.addEventListener('submit', e => this.handleRegister(e));

    // Admin login form
    const adminForm = document.getElementById('admin-login-form');
    if (adminForm) adminForm.addEventListener('submit', e => this.handleAdminLogin(e));

    // Forgot password form
    const forgotForm = document.getElementById('forgot-form');
    if (forgotForm) forgotForm.addEventListener('submit', e => this.handleForgotPassword(e));

    // Reset password form
    const resetForm = document.getElementById('reset-form');
    if (resetForm) resetForm.addEventListener('submit', e => this.handleResetPassword(e));

    // Forgot password link
    const forgotLink = document.getElementById('forgot-password-link');
    if (forgotLink) {
      forgotLink.addEventListener('click', e => {
        e.preventDefault();
        this._showAuthPane('forgot-pane', null);
      });
    }

    // Back to login button
    const backBtn = document.getElementById('back-to-login-btn');
    if (backBtn) {
      backBtn.addEventListener('click', () => {
        this._showAuthPane('login-pane', document.getElementById('tab-login'));
      });
    }

    // Password toggle (login)
    const toggleLoginPw = document.getElementById('toggle-login-pw');
    if (toggleLoginPw) {
      toggleLoginPw.addEventListener('click', () => {
        const field = document.getElementById('login-password');
        const icon  = document.getElementById('login-pw-icon');
        if (field) field.type = field.type === 'password' ? 'text' : 'password';
        if (icon)  icon.className = field.type === 'password' ? 'fa-solid fa-eye' : 'fa-solid fa-eye-slash';
      });
    }

    // Password toggle (register)
    const toggleRegPw = document.getElementById('toggle-reg-pw');
    if (toggleRegPw) {
      toggleRegPw.addEventListener('click', () => {
        const field = document.getElementById('reg-password');
        const icon  = document.getElementById('reg-pw-icon');
        if (field) field.type = field.type === 'password' ? 'text' : 'password';
        if (icon)  icon.className = field.type === 'password' ? 'fa-solid fa-eye' : 'fa-solid fa-eye-slash';
      });
    }

    // Password strength meter (register)
    const regPass = document.getElementById('reg-password');
    if (regPass) regPass.addEventListener('input', () => this._updateStrengthBar('reg-pw-fill', 'reg-pw-label', regPass.value));

    // Password strength meter (change password)
    const cpNew = document.getElementById('cp-new');
    if (cpNew) cpNew.addEventListener('input', () => this._updateStrengthBar('cp-pw-fill', 'cp-pw-label', cpNew.value));

    // Logout buttons
    ['logout-btn', 'logout-btn-profile'].forEach(id => {
      const btn = document.getElementById(id);
      if (btn) btn.addEventListener('click', () => this.handleLogout());
    });
  },

  // ── Check session on page load ──
  checkAuthStatus: async function () {
    try {
      const res  = await fetch('/api/auth/me');
      const data = await res.json();
      if (data.status === 'success' && data.authenticated && data.user) {
        this.currentUser = data.user;
        Navigation.showAppShell(data.user);
      } else {
        this.currentUser = null;
        Navigation.showAuthScreen();
      }
    } catch (err) {
      console.error('[Auth] Session check error:', err);
      Navigation.showAuthScreen();
    }
  },

  // ── Login ──
  handleLogin: async function (e) {
    e.preventDefault();
    const email    = document.getElementById('login-email')?.value.trim();
    const password = document.getElementById('login-password')?.value;
    const btn      = document.getElementById('login-submit-btn');
    const errBox   = document.getElementById('login-error');
    const errMsg   = document.getElementById('login-error-msg');

    this._hideError(errBox);
    if (!email || !password) { this._showError(errBox, errMsg, 'Please enter both email and password.'); return; }

    this._setLoading(btn, true, 'Signing in…');
    try {
      const res  = await fetch('/api/auth/login', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();
      if (data.status === 'success') {
        this.currentUser = data.user;
        Toast.success(`Welcome back, ${data.user.full_name}!`, 'Signed In');
        Navigation.showAppShell(data.user);
      } else {
        this._showError(errBox, errMsg, data.message || 'Invalid credentials.');
        if (data.locked_out) {
          const lockout = document.getElementById('login-lockout');
          const lockMsg = document.getElementById('login-lockout-msg');
          if (lockout) lockout.classList.remove('d-none');
          if (lockMsg) lockMsg.textContent = data.message;
        }
      }
    } catch (err) {
      this._showError(errBox, errMsg, 'Server connection error. Please try again.');
    } finally {
      this._setLoading(btn, false, '<i class="fa-solid fa-right-to-bracket me-2"></i>Sign In to SkinSense');
    }
  },

  // ── Register ──
  handleRegister: async function (e) {
    e.preventDefault();
    const full_name        = document.getElementById('reg-fullname')?.value.trim();
    const email            = document.getElementById('reg-email')?.value.trim();
    const password         = document.getElementById('reg-password')?.value;
    const confirm_password = document.getElementById('reg-confirm')?.value;   // FIXED: was reg-confirm-password
    const consent          = document.getElementById('reg-consent')?.checked; // FIXED: was reg-privacy-check
    const btn              = document.getElementById('reg-submit-btn');
    const errBox           = document.getElementById('register-error');
    const errMsg           = document.getElementById('register-error-msg');

    this._hideError(errBox);

    if (!consent) {
      this._showError(errBox, errMsg, 'Please accept the Privacy Policy to create an account.');
      return;
    }
    if (password !== confirm_password) {
      this._showError(errBox, errMsg, 'Passwords do not match. Please re-enter them.');
      return;
    }

    this._setLoading(btn, true, 'Creating account…');
    try {
      const res  = await fetch('/api/auth/register', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ full_name, email, password, confirm_password })
      });
      const data = await res.json();
      if (data.status === 'success') {
        this.currentUser = data.user;
        Toast.success('Account created! Welcome to SkinSense.', 'Registered');
        Navigation.showAppShell(data.user);
      } else {
        this._showError(errBox, errMsg, data.message || 'Registration failed.');
      }
    } catch (err) {
      this._showError(errBox, errMsg, 'Server connection error. Please try again.');
    } finally {
      this._setLoading(btn, false, '<i class="fa-solid fa-user-plus me-2"></i>Create My Account');
    }
  },

  // ── Admin Login ──
  handleAdminLogin: async function (e) {
    e.preventDefault();
    const email    = document.getElementById('admin-email')?.value.trim();
    const password = document.getElementById('admin-password')?.value;
    const btn      = document.getElementById('admin-submit-btn');
    const errBox   = document.getElementById('admin-login-error');
    const errMsg   = document.getElementById('admin-login-error-msg');

    this._hideError(errBox);
    if (!email || !password) { this._showError(errBox, errMsg, 'Please enter admin credentials.'); return; }

    this._setLoading(btn, true, 'Authenticating…');
    try {
      const res  = await fetch('/api/auth/admin-login', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();
      if (data.status === 'success') {
        this.currentUser = data.user;
        Toast.success('Administrator authenticated.', 'Admin Access');
        Navigation.showAppShell(data.user, 'admin-dashboard');
      } else {
        this._showError(errBox, errMsg, data.message || 'Invalid administrator credentials.');
      }
    } catch (err) {
      this._showError(errBox, errMsg, 'Server connection error.');
    } finally {
      this._setLoading(btn, false, '<i class="fa-solid fa-shield-cat me-2"></i>Authenticate as Admin');
    }
  },

  // ── Forgot Password (real API) ──
  handleForgotPassword: async function (e) {
    e.preventDefault();
    const email  = document.getElementById('forgot-email')?.value.trim();
    const btn    = document.getElementById('forgot-submit-btn');
    const successBox = document.getElementById('forgot-success');
    const tokenDisplay = document.getElementById('forgot-token-display');
    const resetContainer = document.getElementById('reset-form-container');

    if (!email) { Toast.warning('Please enter your email address.'); return; }

    this._setLoading(btn, true, 'Generating token…');
    try {
      const res  = await fetch('/api/auth/forgot-password', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ email })
      });
      const data = await res.json();

      if (data.status === 'success') {
        if (successBox) successBox.classList.remove('d-none');
        if (tokenDisplay && data.reset_token) {
          tokenDisplay.textContent = data.reset_token;
          // Pre-fill token field
          const tokenInput = document.getElementById('reset-token-input');
          if (tokenInput) tokenInput.value = data.reset_token;
        }
        if (resetContainer) resetContainer.classList.remove('d-none');
      } else {
        Toast.error(data.message || 'Could not process request.', 'Error');
      }
    } catch (err) {
      Toast.error('Server connection error.', 'Error');
    } finally {
      this._setLoading(btn, false, '<i class="fa-solid fa-key me-2"></i>Generate Reset Token');
    }
  },

  // ── Reset Password (real API) ──
  handleResetPassword: async function (e) {
    e.preventDefault();
    const token    = document.getElementById('reset-token-input')?.value.trim();
    const password = document.getElementById('reset-new-pw')?.value;
    const confirm  = document.getElementById('reset-confirm-pw')?.value;

    if (!token || !password) { Toast.warning('Please enter the reset token and a new password.'); return; }
    if (password !== confirm) { Toast.error('Passwords do not match.'); return; }

    try {
      const res  = await fetch('/api/auth/reset-password', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ token, new_password: password, confirm_password: confirm })
      });
      const data = await res.json();
      if (data.status === 'success') {
        Toast.success('Password reset successfully. Please log in.', 'Success');
        this._showAuthPane('login-pane', document.getElementById('tab-login'));
      } else {
        Toast.error(data.message || 'Password reset failed.', 'Error');
      }
    } catch (err) {
      Toast.error('Server connection error.', 'Error');
    }
  },

  // ── Logout ──
  handleLogout: async function () {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) { /* ignore */ }
    this.currentUser = null;
    Navigation.showAuthScreen();
    Toast.info('You have been signed out.', 'Logged Out');
  },

  // ── Helpers ──
  _showAuthPane: function (paneId, activeBtn) {
    document.querySelectorAll('.auth-pane').forEach(p => p.classList.add('d-none'));
    document.querySelectorAll('.auth-tab-pill').forEach(b => b.classList.remove('active'));
    const pane = document.getElementById(paneId);
    if (pane) pane.classList.remove('d-none');
    if (activeBtn) activeBtn.classList.add('active');
  },

  _showError: function (box, msgEl, msg) {
    if (box)   box.classList.remove('d-none');
    if (msgEl) msgEl.textContent = msg;
  },

  _hideError: function (box) {
    if (box) box.classList.add('d-none');
  },

  _setLoading: function (btn, loading, label) {
    if (!btn) return;
    btn.disabled = loading;
    if (loading) {
      btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin me-2"></i>' + label;
    } else {
      btn.innerHTML = label;
    }
  },

  _updateStrengthBar: function (fillId, labelId, password) {
    const fill  = document.getElementById(fillId);
    const label = document.getElementById(labelId);
    if (!fill || !label) return;
    if (!password) { fill.style.width = '0%'; label.textContent = ''; return; }

    let score = 0;
    if (password.length >= 8)                    score += 25;
    if (/[A-Z]/.test(password))                  score += 25;
    if (/[0-9]/.test(password))                  score += 25;
    if (/[^A-Za-z0-9]/.test(password))           score += 25;

    fill.style.width = score + '%';
    const levels = { 0:'', 25:'Weak', 50:'Fair', 75:'Good', 100:'Strong' };
    const colors = { 0:'', 25:'#f43f5e', 50:'#f59e0b', 75:'#3b82f6', 100:'#10b981' };
    label.textContent  = levels[score] || 'Fair';
    label.style.color  = colors[score] || 'var(--text-muted)';
    fill.style.background = colors[score] || '#e2e8f0';
  }
};

document.addEventListener('DOMContentLoaded', () => {
  Auth.init();
});
