/**
 * SkinSense — History / Reports Module v2.1
 * Fixes & Features:
 *  - Full Start Date & End Date range filtering (inclusive of boundary dates)
 *  - Instant UI results update on date / search / condition change
 *  - Preserves search and condition filters alongside date filtering
 *  - Bulletproof timezone and ISO date format handling
 *  - Localized empty results message across supported languages
 *  - Refresh re-fetches latest filtered records without resetting UI filters
 */
window.HistoryModule = {
  _view: 'card', // 'card' | 'table'
  _currentId: null,

  init: function () {
    window.SectionHooks['history'] = () => this.load();
    this._bindControls();
    window.addEventListener('languageChanged', () => this.load());
  },

  _bindControls: function () {
    // Refresh button
    const refreshBtn = document.getElementById('hist-refresh-btn');
    if (refreshBtn) refreshBtn.addEventListener('click', () => this.load());

    // Search input (debounced)
    const search = document.getElementById('hist-search');
    if (search) search.addEventListener('input', debounce(() => this.load(), 350));

    // Condition / class filter
    const classFilter = document.getElementById('hist-class-filter');
    if (classFilter) classFilter.addEventListener('change', () => this.load());

    // Date filters — listen to both 'change' and 'input' for instant UI update
    ['hist-date-from', 'hist-date-to'].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener('change', () => this.load());
        el.addEventListener('input', () => this.load());
      }
    });

    // View toggle (card / table)
    const toggleBtn = document.getElementById('hist-toggle-view');
    const viewIcon  = document.getElementById('hist-view-icon');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        this._view = this._view === 'card' ? 'table' : 'card';
        const cardView  = document.getElementById('hist-card-view');
        const tableView = document.getElementById('hist-table-view');
        if (this._view === 'card') {
          cardView?.classList.remove('d-none');
          tableView?.classList.add('d-none');
          if (viewIcon) viewIcon.className = 'fa-solid fa-grip';
        } else {
          cardView?.classList.add('d-none');
          tableView?.classList.remove('d-none');
          if (viewIcon) viewIcon.className = 'fa-solid fa-list';
        }
      });
    }

    // Modal PDF download button
    const modalPdf = document.getElementById('modal-download-pdf');
    if (modalPdf) {
      modalPdf.addEventListener('click', () => {
        if (this._currentId) this._downloadPdf(this._currentId);
      });
    }
  },

  load: async function () {
    const search      = document.getElementById('hist-search')?.value?.trim()     || '';
    const classFilter = document.getElementById('hist-class-filter')?.value || 'all';
    const dateFrom    = document.getElementById('hist-date-from')?.value   || '';
    const dateTo      = document.getElementById('hist-date-to')?.value     || '';

    const params = new URLSearchParams({ search, class_filter: classFilter });
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo)   params.set('date_to', dateTo);

    // Show skeleton / loading indicator
    const cardsCont = document.getElementById('hist-cards-container');
    const tableCont = document.getElementById('hist-table-body');
    if (cardsCont) cardsCont.innerHTML = this._skeletonCards(3);
    if (tableCont) tableCont.innerHTML = `<tr><td colspan="7" class="text-center py-5 text-muted"><i class="fa-solid fa-spinner fa-spin me-2"></i>Loading reports…</td></tr>`;

    try {
      const res  = await fetch('/api/history?' + params.toString());
      const data = await res.json();
      if (data.status === 'success') {
        const assessments = data.assessments || [];
        if (!assessments.length) {
          const msg = window.I18nModule ? window.I18nModule.t('no_matching_reports') : 'No assessment records match your selected filters or date range.';
          this._renderEmpty(msg);
        } else {
          this._renderCards(assessments);
          this._renderTable(assessments);
        }
      } else {
        this._renderEmpty(data.message || 'Could not load assessments.');
      }
    } catch (err) {
      this._renderEmpty('Network error — please refresh.');
    }
  },

  _formatDate: function (dateVal) {
    if (!dateVal) return 'N/A';
    try {
      const safeStr = String(dateVal).replace(/-/g, '/').replace('T', ' ');
      const d = new Date(safeStr);
      if (isNaN(d.getTime())) return String(dateVal).split(' ')[0] || 'N/A';
      return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (e) {
      return String(dateVal).split(' ')[0] || 'N/A';
    }
  },

  _renderCards: function (items) {
    const cont = document.getElementById('hist-cards-container');
    if (!cont) return;
    if (!items.length) {
      const msg = window.I18nModule ? window.I18nModule.t('no_matching_reports') : 'No assessment records match your selected filters or date range.';
      this._renderEmpty(msg);
      return;
    }
    cont.innerHTML = items.map(item => {
      const dt    = this._formatDate(item.created_at);
      const score = ((item.model_score || 0) * 100).toFixed(1);
      const sev   = item.severity_category || 'Mild';
      const isReviewed = item.dermatologist_diagnosis || item.dermatologist_notes || item.review_status === 'completed';
      const sevStyles = {
        Mild:     'background:var(--emerald-50);color:var(--emerald-600);',
        Moderate: 'background:var(--amber-50);color:var(--amber-600);',
        High:     'background:var(--rose-50);color:var(--rose-600);',
        Urgent:   'background:var(--rose-500);color:#fff;',
      };
      const imgTag = item.image_filename
        ? `<img src="/uploads/${item.image_filename}" class="rounded-2 object-fit-cover" width="56" height="56" alt="Scan" onerror="this.style.display='none'">`
        : `<div class="rounded-2 bg-teal-soft d-flex align-items-center justify-content-center" style="width:56px;height:56px;flex-shrink:0;"><i class="fa-solid fa-microscope text-teal"></i></div>`;

      return `<div class="col-md-6 col-lg-4">
        <div class="card p-3 h-100">
          <div class="d-flex align-items-center gap-3 mb-3">
            ${imgTag}
            <div class="min-w-0">
              <div class="fw-700 text-truncate">${item.predicted_name || 'Unknown'}</div>
              <div class="small text-muted">${item.id}</div>
              <div class="small text-muted">${dt}</div>
            </div>
          </div>
          <div class="d-flex justify-content-between align-items-center mb-2">
            <span class="small fw-600 px-2 py-1 rounded-pill" style="${sevStyles[sev] || sevStyles.Mild}">${sev}</span>
            ${isReviewed
              ? `<span class="badge-pill badge-emerald" style="font-size:.7rem;"><i class="fa-solid fa-user-doctor me-1"></i>Doctor Reviewed</span>`
              : `<span class="small text-muted">${score}% match</span>`}
          </div>
          <div class="d-flex gap-2 mt-auto">
            <button class="btn btn-primary btn-sm flex-grow-1" onclick="HistoryModule.openDetail('${item.id}')">
              <i class="fa-solid fa-eye me-1"></i>View
            </button>
            <button class="btn btn-ghost btn-sm" onclick="HistoryModule._downloadPdf('${item.id}')" title="Download PDF">
              <i class="fa-solid fa-file-pdf"></i>
            </button>
            <button class="btn btn-ghost btn-sm text-danger" onclick="HistoryModule.deleteRecord('${item.id}')" title="Delete">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </div>
      </div>`;
    }).join('');
  },

  _renderTable: function (items) {
    const tbody = document.getElementById('hist-table-body');
    if (!tbody) return;
    if (!items.length) {
      const msg = window.I18nModule ? window.I18nModule.t('no_matching_reports') : 'No assessment records match your selected filters or date range.';
      tbody.innerHTML = `<tr><td colspan="7" class="text-center py-5 text-muted">${msg}</td></tr>`;
      return;
    }
    tbody.innerHTML = items.map(item => {
      const dt    = this._formatDate(item.created_at);
      const score = ((item.model_score || 0) * 100).toFixed(1);
      const sev   = item.severity_category || 'Mild';
      const isReviewed = item.dermatologist_diagnosis || item.dermatologist_notes || item.review_status === 'completed';
      const status = isReviewed
        ? '<span class="badge-pill badge-emerald" style="font-size:.7rem;"><i class="fa-solid fa-user-doctor me-1"></i>Reviewed</span>'
        : item.is_escalated
          ? '<span class="badge-pill badge-rose" style="font-size:.7rem;">Flagged</span>'
          : '<span class="badge-pill badge-teal" style="font-size:.7rem;">Completed</span>';
      return `<tr>
        <td class="ps-4 fw-600 text-muted small">${item.id}</td>
        <td class="small text-muted">${dt}</td>
        <td class="fw-600">${item.predicted_name || 'Unknown'}</td>
        <td><span class="badge-pill badge-teal" style="font-size:.75rem;">${score}%</span></td>
        <td><span class="small fw-600">${sev}</span> <span class="small text-muted">(${Math.round(item.severity_score || 0)})</span></td>
        <td>${status}</td>
        <td class="text-end pe-4">
          <button class="btn btn-sm btn-primary me-1" onclick="HistoryModule.openDetail('${item.id}')">
            <i class="fa-solid fa-eye me-1"></i>View
          </button>
          <button class="btn btn-sm btn-ghost" onclick="HistoryModule._downloadPdf('${item.id}')" title="PDF">
            <i class="fa-solid fa-file-pdf"></i>
          </button>
          <button class="btn btn-sm btn-ghost text-teal" onclick="TrackingModule.openAddToTrackModal('${item.id}')" title="Add to Lesion Track" aria-label="Add to Lesion Track">
            <i class="fa-solid fa-link"></i>
          </button>
          <button class="btn btn-sm btn-ghost text-danger" onclick="HistoryModule.deleteRecord('${item.id}')" title="Delete">
            <i class="fa-solid fa-trash"></i>
          </button>
        </td>
      </tr>`;
    }).join('');
  },

  // ── Open detail modal ──
  openDetail: async function (assessmentId) {
    this._currentId = assessmentId;
    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('scanDetailModal'));
    const body  = document.getElementById('scan-detail-modal-body');
    if (body) body.innerHTML = `<div class="text-center py-5"><i class="fa-solid fa-spinner fa-spin fa-2x text-teal"></i></div>`;
    modal.show();

    try {
      const res  = await fetch(`/api/history/${assessmentId}`);
      const data = await res.json();
      if (data.status === 'success') {
        const asm = data.assessment;
        const vis = asm.visual_explanation;
        const score = ((asm.model_score || 0) * 100).toFixed(1);
        const dt = this._formatDate(asm.created_at);

        const isReviewed = asm.dermatologist_diagnosis || asm.dermatologist_notes || asm.review_status === 'completed';

        const doctorVerdictBox = isReviewed ? `
          <div class="p-3 mb-3 border rounded-lg" style="background:#f0fdf4; border-color:#86efac !important;">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <div class="fw-700 text-emerald-700" style="color:#15803d;">
                <i class="fa-solid fa-user-doctor me-2"></i>Dermatologist Clinical Verdict
              </div>
              <span class="badge-pill badge-emerald"><i class="fa-solid fa-circle-check me-1"></i>Doctor Verified</span>
            </div>
            ${asm.dermatologist_diagnosis ? `<div class="fw-700 fs-6 text-dark mb-1">Diagnosis / Verdict: <span class="text-teal">${asm.dermatologist_diagnosis}</span></div>` : ''}
            ${asm.dermatologist_notes ? `<div class="small text-muted mt-2"><strong>Doctor's Clinical Notes:</strong><br>${asm.dermatologist_notes}</div>` : ''}
          </div>
        ` : '';

        body.innerHTML = `
          <div class="row g-4">
            <div class="col-md-5 text-center">
              <div class="border rounded-lg p-2 bg-teal-soft mb-2">
                ${vis?.overlay_url
                  ? `<img src="${vis.overlay_url}" class="img-fluid rounded-2" style="max-height:220px;object-fit:contain;" alt="Heatmap">`
                  : asm.image_filename
                    ? `<img src="/uploads/${asm.image_filename}" class="img-fluid rounded-2" style="max-height:220px;object-fit:contain;" alt="Scan">`
                    : `<div class="p-5 text-muted"><i class="fa-solid fa-image fa-3x"></i><br><small>No image saved</small></div>`}
                <div class="small text-muted mt-1">${vis?.overlay_url ? 'Grad-CAM Heatmap' : 'Uploaded Photo'}</div>
              </div>
              <button class="btn btn-ghost btn-sm w-100" onclick="HistoryModule._downloadPdf('${asm.id}')">
                <i class="fa-solid fa-file-pdf me-1 text-rose"></i>Download PDF Report
              </button>
            </div>
            <div class="col-md-7">
              <h4 class="fw-700 mb-1">${asm.predicted_name || 'Unknown Condition'}</h4>
              <div class="text-muted small mb-3">${dt} · ID: ${asm.id}</div>
              <div class="d-flex flex-wrap gap-2 mb-3">
                <span class="badge-pill badge-teal">AI Match: ${score}%</span>
                <span class="badge-pill badge-neutral">${asm.quality_status || 'Optimal'} Quality</span>
                ${asm.severity_category ? `<span class="badge-pill badge-amber">${asm.severity_category} Severity</span>` : ''}
                ${isReviewed
                  ? `<span class="badge-pill badge-emerald"><i class="fa-solid fa-user-doctor me-1"></i>Doctor Reviewed</span>`
                  : asm.is_escalated ? `<span class="badge-pill badge-rose"><i class="fa-solid fa-clock me-1"></i>Pending Doctor Review</span>` : ''}
              </div>

              ${doctorVerdictBox}

              <div class="p-3 bg-teal-soft border-teal rounded-lg mb-3">
                <div class="fw-600 small mb-1"><i class="fa-solid fa-circle-info text-teal me-1"></i>Clinical Summary</div>
                <div class="text-muted small">${asm.clinical_summary || 'AI assessment complete.'}</div>
              </div>
              <div class="alert-inline warning">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <div class="small">${asm.disclaimer || 'This is an AI-assisted assessment, not a clinical diagnosis. Consult a dermatologist for evaluation.'}</div>
              </div>
            </div>
          </div>`;
      } else {
        body.innerHTML = `<div class="text-center py-4 text-danger"><i class="fa-solid fa-circle-exclamation me-2"></i>${data.message || 'Report not found.'}</div>`;
      }
    } catch (err) {
      body.innerHTML = `<div class="text-center py-4 text-danger">Connection error loading report.</div>`;
    }
  },

  _downloadPdf: function (assessmentId) {
    const link = document.createElement('a');
    link.href     = `/api/report/${assessmentId}`;
    link.download = `SkinSense_Report_${assessmentId}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    Toast.info('Downloading PDF report…', 'Download');
  },

  deleteRecord: async function (assessmentId) {
    if (!confirm(`Are you sure you want to delete report ${assessmentId}? This cannot be undone.`)) return;
    try {
      const res  = await fetch(`/api/history/${assessmentId}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.status === 'success') {
        Toast.success('Assessment record deleted.', 'Deleted');
        this.load();
      } else {
        Toast.error(data.message || 'Deletion failed.', 'Error');
      }
    } catch (err) {
      Toast.error('Server error during deletion.', 'Error');
    }
  },

  _skeletonCards: function (n) {
    return Array(n).fill(`<div class="col-md-4"><div class="skeleton" style="height:180px;border-radius:12px;"></div></div>`).join('');
  },

  _renderEmpty: function (msg) {
    const localizedMsg = msg || (window.I18nModule ? window.I18nModule.t('no_matching_reports') : 'No assessment records match your selected filters or date range.');
    const scanBtnText = window.I18nModule ? window.I18nModule.t('start_assessment') : 'Run New Scan';
    const cont = document.getElementById('hist-cards-container');
    if (cont) {
      cont.innerHTML = `<div class="col-12">
        <div class="card p-5 text-center">
          <i class="fa-solid fa-folder-open fa-2x text-muted mb-3"></i>
          <p class="text-muted mb-3">${localizedMsg}</p>
          <button class="btn btn-primary btn-sm mx-auto" onclick="navigateTo('scanner')" style="width:fit-content;">
            <i class="fa-solid fa-camera me-2"></i>${scanBtnText}
          </button>
        </div></div>`;
    }
    const tbody = document.getElementById('hist-table-body');
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center py-5 text-muted">${localizedMsg}</td></tr>`;
    }
  }
};

// ── Debounce helper ──
function debounce(fn, ms) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), ms);
  };
}

// ── Expose global helpers ──
window.viewHistoryDetails   = id => HistoryModule.openDetail(id);
window.deleteHistoryRecord  = id => HistoryModule.deleteRecord(id);

document.addEventListener('DOMContentLoaded', () => {
  HistoryModule.init();
});
