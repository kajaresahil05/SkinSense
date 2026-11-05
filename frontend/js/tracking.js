/**
 * SkinSense — Lesion Tracking Module v2.0
 * Wires: track list, create track modal, add-to-track modal,
 *        track detail view with progression analysis.
 */
window.TrackingModule = {
  _trackList: [],

  init: function () {
    window.SectionHooks['tracking'] = () => {
      const trackId = this._timelineOnEnter;
      this._timelineOnEnter = null;
      if (trackId) this.viewTrack(trackId);
      else this.loadTracks();
    };
    this._bindControls();
    window.addEventListener('languageChanged', () => {
      if (this._openTrack) this.viewTrack(this._openTrack.id);
      else if (document.getElementById('page-tracking')?.classList.contains('active')) this.loadTracks();
    });
  },

  _bindControls: function () {
    // Create new track button
    const createBtn = document.getElementById('create-track-btn');
    if (createBtn) createBtn.addEventListener('click', () => this._showCreateTrackPrompt());

    // Add-to-track modal confirm
    const confirmBtn = document.getElementById('confirm-add-track-btn');
    if (confirmBtn) confirmBtn.addEventListener('click', () => this._confirmAddToTrack());
  },

  loadTracks: async function () {
    this._openTrack = null;
    const cont = document.getElementById('tracking-container');
    if (cont) cont.innerHTML = `<div class="text-center py-5 text-muted"><i class="fa-solid fa-spinner fa-spin me-2"></i>Loading lesion tracks…</div>`;

    try {
      const res  = await fetch('/api/tracks');
      const data = await res.json();
      this._trackList = data.tracks || [];
      this._renderTracks(this._trackList);
    } catch (err) {
      const cont = document.getElementById('tracking-container');
      if (cont) cont.innerHTML = `<div class="card p-4 text-danger text-center">Failed to load tracks.</div>`;
    }
  },

  _renderTracks: function (tracks) {
    const cont = document.getElementById('tracking-container');
    if (!cont) return;

    const t = window.I18nModule ? window.I18nModule.t.bind(window.I18nModule) : (k => k);

    if (!tracks || !tracks.length) {
      cont.innerHTML = `
        <div class="card p-5 text-center">
          <i class="fa-solid fa-chart-line fa-2x text-muted mb-3"></i>
          <h5 class="fw-700 mb-2">${t('no_tracks_yet') || 'No Lesion Tracks Yet'}</h5>
          <p class="text-muted mb-4">${t('create_track_desc') || 'Create a track to monitor a specific skin lesion over time and detect changes.'}</p>
          <button class="btn btn-primary mx-auto" onclick="TrackingModule._showCreateTrackPrompt()" style="width:fit-content;">
            <i class="fa-solid fa-plus me-2"></i>${t('create_first_track') || 'Create First Track'}
          </button>
        </div>`;
      return;
    }

    const regionLabels = {
      face: t('region_face') || 'Face / Neck',
      arm:  t('region_arm') || 'Arm / Hand',
      leg:  t('region_leg') || 'Leg / Foot',
      torso:t('region_torso') || 'Torso / Back',
      scalp:t('region_scalp') || 'Scalp',
      other:t('region_other') || 'Other'
    };

    const viewTimelineText = t('view_timeline') || 'View Timeline';
    const scansText = t('scans') || 'scans';

    cont.innerHTML = `<div class="row g-4">` + tracks.map(track => {
      const created = track.created_at ? new Date(track.created_at).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' }) : '';
      const region  = regionLabels[track.body_region] || track.body_region || 'Unknown Region';
      return `<div class="col-md-6 col-lg-4">
        <div class="card p-4 h-100">
          <div class="d-flex justify-content-between align-items-start mb-3">
            <div>
              <div class="fw-700">${track.track_name}</div>
              <div class="small text-muted"><i class="fa-solid fa-location-dot me-1"></i>${region}</div>
              <div class="small text-muted">Created: ${created}</div>
            </div>
            <span class="badge-pill badge-teal" style="font-size:.7rem;">${track.assessment_count || 0} ${scansText}</span>
          </div>
          ${track.notes ? `<p class="small text-muted mb-3">${track.notes}</p>` : ''}
          <div class="d-flex gap-2 mt-auto">
            <button class="btn btn-primary btn-sm flex-grow-1" onclick="TrackingModule.viewTrack(${track.id})">
              <i class="fa-solid fa-chart-line me-1"></i>${viewTimelineText}
            </button>
            <button class="btn btn-ghost btn-sm text-danger" onclick="TrackingModule.deleteTrack(${track.id}, '${track.track_name}')">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </div>
      </div>`;
    }).join('') + `</div>`;
  },

  openTimeline: function (trackId) {
    this._timelineOnEnter = trackId;
    navigateTo('tracking');
  },

  startScan: function () {
    if (!this._openTrack) return;
    navigateTo('scanner');
    ScannerModule.setTrack(this._openTrack);
  },

  viewTrack: async function (trackId) {
    const cont = document.getElementById('tracking-container');
    if (cont) cont.innerHTML = `<div class="text-center py-5 text-muted"><i class="fa-solid fa-spinner fa-spin me-2"></i>Loading track timeline…</div>`;

    try {
      const res  = await fetch(`/api/tracks/${trackId}`);
      const data = await res.json();
      if (data.status !== 'success') { Toast.error('Could not load track.', 'Error'); return; }

      const track       = data.track;
      this._openTrack = track;
      const assessments = data.assessments || [];
      const prog        = data.progression || {};

      let html = `
        <button class="btn btn-ghost btn-sm mb-4" onclick="TrackingModule.loadTracks()">
          <i class="fa-solid fa-arrow-left me-1"></i>Back to Tracks
        </button>
        <div class="card p-4 mb-4">
          <h4 class="fw-700 mb-1">${track.track_name}</h4>
          <div class="text-muted small mb-3">${track.body_region || ''} ${track.notes ? '· ' + track.notes : ''}</div>
          <div class="mb-3">
            <button class="btn btn-primary btn-sm" onclick="TrackingModule.startScan()">
              <i class="fa-solid fa-camera me-1"></i>Scan This Lesion
            </button>
          </div>`;

      // Progression summary
      if (prog.has_progression) {
        const trendColor = { stable:'teal', worsening:'rose', improving:'emerald' }[prog.severity_trend] || 'teal';
        html += `<div class="row g-3 mb-3">
          <div class="col-md-4">
            <div class="stat-card">
              <div class="stat-icon teal"><i class="fa-solid fa-file-medical"></i></div>
              <div><div class="stat-value">${prog.total_assessments}</div><div class="stat-label">Total Scans</div></div>
            </div>
          </div>
          <div class="col-md-4">
            <div class="stat-card">
              <div class="stat-icon ${trendColor}"><i class="fa-solid fa-arrow-trend-${prog.severity_trend === 'improving' ? 'down' : prog.severity_trend === 'worsening' ? 'up' : 'right'}"></i></div>
              <div><div class="stat-value text-capitalize">${prog.severity_trend}</div><div class="stat-label">Severity Trend</div></div>
            </div>
          </div>
          <div class="col-md-4">
            <div class="stat-card">
              <div class="stat-icon ${prog.severity_change > 0 ? 'rose' : 'emerald'}">
                <i class="fa-solid fa-${prog.severity_change > 0 ? 'arrow-up' : 'arrow-down'}"></i>
              </div>
              <div><div class="stat-value">${prog.severity_change > 0 ? '+' : ''}${prog.severity_change.toFixed(1)}</div><div class="stat-label">Score Change</div></div>
            </div>
          </div>
        </div>`;

        // Alerts
        (prog.alerts || []).forEach(alert => {
          const type = alert.type === 'urgent' ? 'danger' : alert.type === 'warning' ? 'warning' : 'info';
          html += `<div class="alert-inline ${type} mb-3">
            <i class="fa-solid fa-${alert.type === 'urgent' ? 'triangle-exclamation' : 'circle-info'}"></i>
            <div class="small">${alert.message}</div>
          </div>`;
        });
      }
      html += `</div>`;

      // Assessment timeline
      html += `<div class="section-header mb-3"><div><h5 class="section-title">Assessment Timeline</h5></div></div>`;
      if (!assessments.length) {
        html += `<div class="card p-4 text-center text-muted">
          <p class="mb-2">No assessments linked yet. Scan this lesion or add a saved scan from History.</p>
          <button class="btn btn-ghost btn-sm mx-auto" onclick="navigateTo('history')">Open Scan History</button>
        </div>`;
      } else {
        html += assessments.map((asm, i) => {
          const dt = asm.created_at ? new Date(asm.created_at).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' }) : '';
          const score = ((asm.model_score || 0) * 100).toFixed(1);
          return `<div class="card p-4 mb-3" style="border-left:3px solid var(--teal-500);">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <div class="fw-600">${asm.predicted_name || 'Unknown'}</div>
              <div class="small text-muted">${dt}</div>
            </div>
            <div class="d-flex gap-2 flex-wrap">
              <span class="badge-pill badge-teal" style="font-size:.7rem;">${score}% match</span>
              <span class="badge-pill badge-neutral" style="font-size:.7rem;">Severity: ${Math.round(asm.severity_score || 0)}</span>
              ${asm.change_notes ? `<span class="badge-pill badge-blue" style="font-size:.7rem;">${asm.change_notes}</span>` : ''}
            </div>
          </div>`;
        }).join('');
      }

      if (cont) cont.innerHTML = html;
    } catch (err) {
      const cont = document.getElementById('tracking-container');
      if (cont) cont.innerHTML = `<div class="card p-4 text-danger text-center">Error loading track details.</div>`;
    }
  },

  deleteTrack: async function (trackId, name) {
    if (!confirm(`Delete track "${name}"? All linked assessment entries will be removed from this track.`)) return;
    try {
      const res  = await fetch(`/api/tracks/${trackId}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.status === 'success') { Toast.success('Track deleted.', 'Tracking'); this.loadTracks(); }
      else Toast.error(data.message || 'Delete failed.', 'Error');
    } catch (err) { Toast.error('Server error.', 'Error'); }
  },

  _showCreateTrackPrompt: function () {
    const name = prompt('Track name (e.g. "Left shoulder mole"):');
    if (!name || !name.trim()) return;
    const region = prompt('Body region (face/arm/leg/torso/scalp/other):') || 'other';
    this._createTrack(name.trim(), region.trim());
  },

  _createTrack: async function (trackName, bodyRegion, notes) {
    try {
      const res  = await fetch('/api/tracks', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ track_name: trackName, body_region: bodyRegion, notes: notes || '' })
      });
      const data = await res.json();
      if (data.status === 'success') { Toast.success('Lesion track created!', 'Tracking'); this.loadTracks(); }
      else Toast.error(data.message || 'Create failed.', 'Error');
    } catch (err) { Toast.error('Server error.', 'Error'); }
  },

  // ── Add to Track Modal ──
  openAddToTrackModal: async function (assessmentId) {
    window._pendingTrackAssessmentId = assessmentId;
    const select = document.getElementById('track-select');
    if (select) {
      select.innerHTML = '<option value="">Loading tracks…</option>';
      try {
        const res  = await fetch('/api/tracks');
        const data = await res.json();
        const tracks = data.tracks || [];
        select.innerHTML = tracks.length
          ? '<option value="">— Select existing track —</option>' + tracks.map(t => `<option value="${t.id}">${t.track_name}</option>`).join('')
          : '<option value="">No tracks yet — create one below</option>';
      } catch (e) {
        select.innerHTML = '<option value="">Could not load tracks</option>';
      }
    }
    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('addTrackModal'));
    modal.show();
  },

  linkAssessment: async function (trackId, assessmentId) {
    const res = await fetch(`/api/tracks/${trackId}/add`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ assessment_id: assessmentId })
    });
    const data = await res.json();
    if (!res.ok || data.status !== 'success') {
      throw new Error(data.message || 'Could not add assessment to track.');
    }
  },

  _confirmAddToTrack: async function () {
    const assessmentId = window._pendingTrackAssessmentId;
    const trackSelect  = document.getElementById('track-select');
    const newName      = document.getElementById('new-track-name')?.value.trim();
    const newRegion    = document.getElementById('new-track-region')?.value;
    const btn          = document.getElementById('confirm-add-track-btn');

    if (!assessmentId) { Toast.warning('No assessment selected.'); return; }
    if (btn) btn.disabled = true;

    try {
      let trackId = trackSelect?.value;

      // Create new track if needed
      if (!trackId && newName) {
        const res  = await fetch('/api/tracks', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ track_name: newName, body_region: newRegion || 'other' })
        });
        const data = await res.json();
        if (data.status !== 'success') { Toast.error(data.message || 'Create failed.', 'Error'); return; }
        trackId = data.track.id;
      }

      if (!trackId) { Toast.warning('Please select or create a track.'); return; }

      await this.linkAssessment(trackId, assessmentId);
      Toast.success('Assessment added to track!', 'Tracking');
      bootstrap.Modal.getInstance(document.getElementById('addTrackModal'))?.hide();
      if (document.getElementById('new-track-name')) document.getElementById('new-track-name').value = '';
    } catch (err) {
      Toast.error(err.message || 'Could not add assessment to track.', 'Error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  TrackingModule.init();
});
