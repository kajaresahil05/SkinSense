/**
 * SkinSense Patient Dashboard Controller — Fixed v2.0
 * Fixes:
 *  - Fetches /api/history (not /api/patient/assessments)
 *  - Correct field mapping: predicted_name, model_score, severity_category
 *  - Fetches /api/tracks for active track count
 *  - Dynamic time-of-day greeting
 *  - Shows user's actual name from Auth.currentUser
 *  - Renders proper card view with correct image URL
 */
window.Dashboard = {
  init: function () {
    window.SectionHooks['dashboard'] = () => this.loadDashboardData();
  },

  loadDashboardData: async function () {
    this._setWelcomeMessage();
    this._renderStatSkeletons();

    try {
      const [assessRes, trackRes] = await Promise.allSettled([
        fetch('/api/history?limit=10'),
        fetch('/api/tracks')
      ]);

      const assessData = assessRes.status === 'fulfilled' ? await assessRes.value.json() : null;
      const trackData  = trackRes.status === 'fulfilled'  ? await trackRes.value.json()  : null;

      const assessments = (assessData?.status === 'success') ? (assessData.assessments || []) : [];
      const tracks      = (trackData?.status  === 'success') ? (trackData.tracks      || []) : [];

      this.renderDoctorVerdictAlert(assessments);
      this.renderStats(assessments, tracks.length);
      this.renderRecentScans(assessments.slice(0, 5));
      this._renderHealthTips();
      if (window.I18nModule) window.I18nModule.applyLanguage(window.I18nModule.currentLang);

    } catch (err) {
      console.error('[Dashboard] Load error:', err);
      this.renderStats([], 0);
      this.renderRecentScans([]);
    }
  },

  renderDoctorVerdictAlert: function (assessments) {
    const alertCont = document.getElementById('dashboard-verdict-alert');
    if (!alertCont) return;

    // Find the latest assessment that has a doctor verdict or review completion
    const reviewedItem = assessments.find(a => a.dermatologist_diagnosis || a.dermatologist_notes || a.review_status === 'completed' || a.review_status === 'reviewed');
    if (!reviewedItem) {
      alertCont.innerHTML = '';
      return;
    }

    const verdictText = reviewedItem.dermatologist_diagnosis || 'Completed';
    const dateStr = reviewedItem.created_at ? new Date(reviewedItem.created_at.replace(/-/g, '/').replace('T', ' ')).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';

    alertCont.innerHTML = `
      <div class="card p-3 mb-4" style="background:#f0fdf4; border:1.5px solid #86efac !important; border-radius:12px;">
        <div class="d-flex flex-column flex-md-row align-items-md-center justify-content-between gap-3">
          <div class="d-flex align-items-center gap-3">
            <div class="rounded-circle d-flex align-items-center justify-content-center flex-shrink-0" style="width:44px;height:44px;background:#dcfce7;color:#16a34a;">
              <i class="fa-solid fa-user-doctor fa-lg"></i>
            </div>
            <div>
              <div class="fw-700 text-dark fs-6 mb-1">
                <i class="fa-solid fa-circle-check text-emerald me-1"></i>Dermatologist Clinical Verdict Available
              </div>
              <div class="small text-muted">
                Diagnosis / Verdict: <strong class="text-teal">${verdictText}</strong> ${dateStr ? `· Assessment Date: ${dateStr}` : ''}
              </div>
            </div>
          </div>
          <button class="btn btn-primary btn-sm flex-shrink-0" onclick="HistoryModule.openDetail('${reviewedItem.id}')" style="background:#059669;border-color:#059669;font-weight:600;">
            <i class="fa-solid fa-stethoscope me-1"></i>View Full Verdict
          </button>
        </div>
      </div>
    `;
  },

  _setWelcomeMessage: function () {
    const greetEl = document.getElementById('dashboard-welcome');
    const nameEl  = document.getElementById('welcome-name');
    const user    = window.Auth?.currentUser;
    const firstName = user?.full_name?.split(' ')[0] || 'there';

    if (nameEl) {
      nameEl.textContent = firstName;
    }
    if (greetEl) {
      const hour = new Date().getHours();
      const key  = hour < 12 ? 'good_morning' : hour < 17 ? 'good_afternoon' : 'good_evening';
      const greeting = window.I18nModule ? window.I18nModule.t(key) : (hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening');
      greetEl.innerHTML = `${greeting}, <span id="welcome-name">${firstName}</span>! 👋`;
    }
  },

  _renderStatSkeletons: function () {
    ['stat-total-scans', 'stat-last-scan', 'stat-tracks', 'stat-review'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = '—';
    });
  },

  renderStats: function (assessments, trackCount) {
    const total = assessments.length;
    const pending = assessments.filter(a => a.is_escalated && a.review_status !== 'completed' && a.review_status !== 'reviewed').length;
    const reviewed = assessments.filter(a => a.dermatologist_diagnosis || a.review_status === 'completed' || a.review_status === 'reviewed').length;

    const el = id => document.getElementById(id);
    if (el('stat-total-scans')) el('stat-total-scans').textContent = total;
    if (el('stat-tracks'))      el('stat-tracks').textContent      = trackCount;
    if (el('stat-review'))      el('stat-review').textContent      = pending > 0 ? pending : (reviewed > 0 ? `${reviewed} Done` : '0');

    if (el('stat-last-scan')) {
      if (total > 0 && assessments[0].created_at) {
        const d = new Date(assessments[0].created_at.replace(/-/g, '/').replace('T', ' '));
        el('stat-last-scan').textContent = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      } else {
        el('stat-last-scan').textContent = 'None';
      }
    }
  },

  renderRecentScans: function (assessments) {
    const container = document.getElementById('dashboard-recent-scans');
    if (!container) return;

    // Remove skeleton
    const skeleton = document.getElementById('recent-scans-skeleton');
    if (skeleton) skeleton.classList.add('d-none');

    if (!assessments || assessments.length === 0) {
      container.innerHTML = `
        <div class="card p-5 text-center">
          <i class="fa-solid fa-folder-open fa-2x text-muted mb-3"></i>
          <p class="text-muted mb-3">No assessments recorded yet.</p>
          <button class="btn btn-primary btn-sm mx-auto" onclick="navigateTo('scanner')" style="width:fit-content;">
            <i class="fa-solid fa-camera me-2"></i>Start Your First Scan
          </button>
        </div>`;
      return;
    }

    const sevColors = {
      Mild:     { bg: 'var(--emerald-50)',  text: 'var(--emerald-600)', border: 'var(--emerald-500)' },
      Moderate: { bg: 'var(--amber-50)',    text: 'var(--amber-600)',   border: 'var(--amber-500)' },
      High:     { bg: 'var(--rose-50)',     text: 'var(--rose-600)',    border: 'var(--rose-500)' },
    };

    container.innerHTML = `<div class="row g-3">` + assessments.map(scan => {
      const sev    = scan.severity_category || 'Mild';
      const col    = sevColors[sev] || sevColors.Mild;
      const score  = ((scan.model_score || 0) * 100).toFixed(1);
      const date   = scan.created_at ? new Date(scan.created_at.replace(/-/g, '/').replace('T', ' ')).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A';
      const imgSrc = scan.image_filename ? `/uploads/${scan.image_filename}` : '';
      const imgTag = imgSrc
        ? `<img src="${imgSrc}" class="rounded-2 object-fit-cover me-3 flex-shrink-0" width="48" height="48" alt="Scan" onerror="this.style.display='none'">`
        : `<div class="rounded-2 bg-teal-soft d-flex align-items-center justify-content-center me-3 flex-shrink-0" style="width:48px;height:48px;"><i class="fa-solid fa-microscope text-teal"></i></div>`;

      const isReviewed = scan.dermatologist_diagnosis || scan.dermatologist_notes || scan.review_status === 'completed' || scan.review_status === 'reviewed';

      return `<div class="col-md-6 col-lg-4">
        <div class="card p-3 h-100" style="border-left:3px solid ${isReviewed ? '#059669' : col.border};">
          <div class="d-flex align-items-center mb-2">
            ${imgTag}
            <div class="min-w-0">
              <div class="fw-700 text-truncate" style="max-width:160px;">${scan.predicted_name || 'Unknown'}</div>
              <div class="small text-muted">${date}</div>
            </div>
          </div>
          <div class="d-flex justify-content-between align-items-center mt-1">
            ${isReviewed
              ? `<span class="small fw-600 px-2 py-1 rounded-pill" style="background:#ecfdf5;color:#059669;"><i class="fa-solid fa-user-doctor me-1"></i>Doctor Reviewed</span>`
              : `<span class="small" style="background:${col.bg};color:${col.text};padding:2px 10px;border-radius:999px;font-weight:600;">${sev}</span>`}
            <span class="small text-muted">${score}% match</span>
          </div>
          ${isReviewed && scan.dermatologist_diagnosis ? `
          <div class="small fw-600 text-teal mt-2 text-truncate" title="${scan.dermatologist_diagnosis}">
            <i class="fa-solid fa-stethoscope me-1"></i>Verdict: ${scan.dermatologist_diagnosis}
          </div>` : ''}
          <button class="btn btn-ghost btn-sm w-100 mt-2" onclick="HistoryModule.openDetail('${scan.id}')">
            View Report <i class="fa-solid fa-chevron-right ms-1"></i>
          </button>
        </div>
      </div>`;
    }).join('') + `</div>`;

    // Also update the recent-scans-list table if it exists (secondary location)
    const listEl = document.getElementById('recent-scans-list');
    if (listEl) {
      listEl.innerHTML = assessments.map(scan => {
        const dateStr = scan.created_at ? new Date(scan.created_at.replace(/-/g, '/').replace('T', ' ')).toLocaleDateString() : 'N/A';
        const score   = ((scan.model_score || 0) * 100).toFixed(1);
        const sev     = scan.severity_category || 'Mild';
        return `<tr>
          <td class="fw-semibold">${scan.predicted_name || 'Unknown'}</td>
          <td><span class="badge bg-teal-subtle text-teal-dark rounded-pill">${score}%</span></td>
          <td>${sev}</td>
          <td class="text-muted small">${dateStr}</td>
          <td class="text-end">
            <button class="btn btn-sm btn-outline-teal rounded-pill px-3" onclick="HistoryModule.openDetail('${scan.id}')">
              View <i class="fa-solid fa-chevron-right ms-1"></i>
            </button>
          </td>
        </tr>`;
      }).join('');
    }
  },

  _renderHealthTips: function () {
    const t = key => window.I18nModule ? window.I18nModule.t(key) : null;
    const tips = [
      { icon: 'fa-sun',        color: 'amber', text: t('tip_sun') || 'Apply SPF 30+ sunscreen daily, even on cloudy days.' },
      { icon: 'fa-droplet',    color: 'blue',  text: t('tip_water') || 'Keep skin hydrated — drink at least 8 glasses of water.' },
      { icon: 'fa-magnifying-glass', color: 'teal', text: t('tip_moles') || 'Check moles monthly using the ABCDE method.' },
      { icon: 'fa-apple-whole', color: 'emerald', text: t('tip_diet') || 'Eat foods rich in antioxidants for skin health.' },
      { icon: 'fa-moon',       color: 'purple', text: t('tip_sleep') || 'Get 7-9 hours of sleep for skin repair and renewal.' },
    ];
    const container = document.getElementById('health-tips-list');
    if (!container) return;
    container.innerHTML = tips.map(tip => `
      <div class="d-flex align-items-center gap-3 p-3 border-bottom" style="border-color:var(--border-muted)!important;">
        <div style="width:36px;height:36px;border-radius:50%;background:var(--${tip.color}-50,#f0fdfa);display:flex;align-items:center;justify-content:center;flex-shrink:0;">
          <i class="fa-solid ${tip.icon}" style="color:var(--${tip.color}-600,var(--teal-600));font-size:0.85rem;"></i>
        </div>
        <span class="small text-secondary">${tip.text}</span>
      </div>`).join('');
  }
};

document.addEventListener('DOMContentLoaded', () => {
  Dashboard.init();
});
