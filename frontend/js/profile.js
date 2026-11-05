/**
 * SkinSense — Profile Module v2.0
 * Loads/saves patient profile, wires change-password form.
 */
window.ProfileModule = {
  init: function () {
    window.SectionHooks['profile'] = () => this.load();
    this._bindForms();
  },

  load: async function () {
    try {
      const res  = await fetch('/api/auth/profile');
      const data = await res.json();
      if (data.status === 'success') {
        const p = data.profile;
        this._fill('prof-fullname', p.full_name);
        this._fill('prof-email',    p.email);
        this._fill('prof-dob',      p.date_of_birth || '');
        this._fill('prof-phone',    p.phone_number  || '');
        // Fitzpatrick select
        const fitz = document.getElementById('prof-fitzpatrick');
        if (fitz && p.fitzpatrick_type) fitz.value = p.fitzpatrick_type;
        // Avatar initials + display name
        const initials = (p.full_name || 'U').split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
        this._fill('profile-avatar-display', initials);
        this._fill('profile-display-name', p.full_name || '');
        this._fill('profile-email-display', p.email || '');
        const roleBadge = document.getElementById('profile-role-badge');
        if (roleBadge) roleBadge.textContent = p.role === 'admin' ? 'Administrator' : 'Patient';
      }
    } catch (err) {
      console.error('[Profile] Load error:', err);
    }
  },

  _bindForms: function () {
    // Profile form save
    const profileForm = document.getElementById('profile-form');
    if (profileForm) {
      profileForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = profileForm.querySelector('button[type="submit"]');
        const data = {
          full_name:        document.getElementById('prof-fullname')?.value.trim(),
          date_of_birth:    document.getElementById('prof-dob')?.value || null,
          phone_number:     document.getElementById('prof-phone')?.value.trim() || null,
          fitzpatrick_type: document.getElementById('prof-fitzpatrick')?.value || null,
        };
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Saving…'; }
        try {
          const res  = await fetch('/api/auth/profile', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
          });
          const resp = await res.json();
          if (resp.status === 'success') {
            Toast.success('Profile updated successfully.', 'Saved');
            // Update sidebar name
            const sidebarName = document.getElementById('sidebar-user-name');
            if (sidebarName && data.full_name) sidebarName.textContent = data.full_name;
            const dispName = document.getElementById('profile-display-name');
            if (dispName && data.full_name) dispName.textContent = data.full_name;
            const avatar = document.getElementById('profile-avatar-display');
            if (avatar && data.full_name) {
              avatar.textContent = data.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
            }
          } else {
            Toast.error(resp.message || 'Update failed.', 'Error');
          }
        } catch (err) {
          Toast.error('Server connection error.', 'Error');
        } finally {
          if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-floppy-disk me-2"></i>Save Changes'; }
        }
      });
    }

    // Change Password form
    const cpForm = document.getElementById('change-pw-form');
    if (cpForm) {
      // Strength meter
      const cpNew = document.getElementById('cp-new');
      if (cpNew) {
        cpNew.addEventListener('input', () => {
          let score = 0;
          const pw = cpNew.value;
          if (pw.length >= 8) score += 25;
          if (/[A-Z]/.test(pw)) score += 25;
          if (/[0-9]/.test(pw)) score += 25;
          if (/[^A-Za-z0-9]/.test(pw)) score += 25;
          const fill  = document.getElementById('cp-pw-fill');
          const label = document.getElementById('cp-pw-label');
          const colors = { 0:'#e2e8f0', 25:'#f43f5e', 50:'#f59e0b', 75:'#3b82f6', 100:'#10b981' };
          const levels = { 0:'', 25:'Weak', 50:'Fair', 75:'Good', 100:'Strong' };
          if (fill)  { fill.style.width = score + '%'; fill.style.background = colors[score]; }
          if (label) { label.textContent = levels[score] || ''; label.style.color = colors[score]; }
        });
      }

      cpForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = cpForm.querySelector('button[type="submit"]');
        const current_password  = document.getElementById('cp-current')?.value;
        const new_password      = document.getElementById('cp-new')?.value;
        const confirm_password  = document.getElementById('cp-confirm')?.value;

        if (new_password !== confirm_password) {
          Toast.error('New passwords do not match.', 'Error'); return;
        }
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Updating…'; }
        try {
          const res  = await fetch('/api/auth/change-password', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ current_password, new_password, confirm_password })
          });
          const data = await res.json();
          if (data.status === 'success') {
            Toast.success('Password changed successfully.', 'Updated');
            cpForm.reset();
            ['cp-pw-fill','cp-pw-label'].forEach(id => {
              const el = document.getElementById(id);
              if (el) { el.style.width = '0%'; el.textContent = ''; }
            });
          } else {
            Toast.error(data.message || 'Password change failed.', 'Error');
          }
        } catch (err) {
          Toast.error('Server connection error.', 'Error');
        } finally {
          if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-shield-halved me-2"></i>Update Password'; }
        }
      });
    }

    // Logout buttons
    ['logout-btn', 'logout-btn-profile'].forEach(id => {
      const btn = document.getElementById(id);
      if (btn) btn.addEventListener('click', () => Auth.handleLogout());
    });
  },

  _fill: function (id, value) {
    const el = document.getElementById(id);
    if (el) {
      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') el.value = value || '';
      else el.textContent = value || '';
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  ProfileModule.init();
});
