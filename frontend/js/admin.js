/**
 * SkinSense — Admin Dashboard Module v2.1
 * Includes stats, user management (filter/edit/delete), model analytics,
 * review queue (filter/verdict/delete), audit log (filter), and
 * Medical Content Management (filter/add/edit/delete).
 */
window.AdminModule = {
  _classChart: null,
  _perClassChart: null,
  _distChart: null,
  _rawUsers: [],
  _rawReviewItems: [],
  _rawAuditLogs: [],
  _searchTimeout: null,
  _reviewReportToken: null,
  _reviewReportRequest: 0,
  _reviewPageRequest: 0,
  _reviewPage: null,
  _reviewFilterKey: null,
  _reviewSearchTimeout: null,

  init: function () {
    window.SectionHooks['admin-dashboard']  = () => this.loadDashboard();
    window.SectionHooks['admin-users']      = () => this.loadUsers();
    window.SectionHooks['admin-analytics']  = () => this.loadAnalytics();
    window.SectionHooks['admin-review']     = () => this.loadReviewQueue();
    window.SectionHooks['admin-audit']      = () => this.loadAuditLog();
    window.SectionHooks['admin-knowledge']  = () => this.loadKnowledgeBase();
    this._bindControls();
  },

  _bindControls: function () {
    // Review queue refresh & verdict submit
    const refreshQueue = document.getElementById('adm-refresh-queue-btn');
    if (refreshQueue) refreshQueue.addEventListener('click', () => this.loadReviewQueue());

    const verdictBtn = document.getElementById('submit-verdict-btn');
    if (verdictBtn) verdictBtn.addEventListener('click', () => this._submitVerdict());

    const reportConfirm = document.getElementById('review-report-confirm');
    if (reportConfirm) reportConfirm.addEventListener('change', () => this._updateVerdictAccess());
    document.getElementById('verdictModal')?.addEventListener('hidden.bs.modal', () => {
      this._reviewReportRequest++;
      this._reviewReportToken = null;
      document.getElementById('verdict-queue-id').value = '';
      if (reportConfirm) reportConfirm.checked = false;
      this._updateVerdictAccess();
    });

    // KB Add & Edit Forms submit
    const addKbBtn = document.getElementById('adm-add-kb-btn');
    if (addKbBtn) {
      addKbBtn.addEventListener('click', () => {
        const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('addKnowledgeModal'));
        modal.show();
      });
    }

    const addKbForm = document.getElementById('add-kb-form');
    if (addKbForm) {
      addKbForm.addEventListener('submit', e => {
        e.preventDefault();
        this._createKnowledgeBaseItem();
      });
    }

    const editKbForm = document.getElementById('edit-kb-form');
    if (editKbForm) {
      editKbForm.addEventListener('submit', e => {
        e.preventDefault();
        this._saveKnowledgeBaseItem();
      });
    }

    // User Edit Form submit
    const editUserForm = document.getElementById('edit-user-form');
    if (editUserForm) {
      editUserForm.addEventListener('submit', e => {
        e.preventDefault();
        this._saveUser();
      });
    }

    // ── Filter controls event listeners ──
    // User Management filters
    const uSearch = document.getElementById('adm-users-search');
    const uRole   = document.getElementById('adm-users-role-select');
    const uStatus = document.getElementById('adm-users-status-select');
    const uReset  = document.getElementById('adm-users-reset-btn');

    if (uSearch) uSearch.addEventListener('input', () => this._filterAndRenderUsers());
    if (uRole)   uRole.addEventListener('change', () => this._filterAndRenderUsers());
    if (uStatus) uStatus.addEventListener('change', () => this._filterAndRenderUsers());
    if (uReset) {
      uReset.addEventListener('click', () => {
        if (uSearch) uSearch.value = '';
        if (uRole)   uRole.value = 'all';
        if (uStatus) uStatus.value = 'all';
        this._filterAndRenderUsers();
      });
    }

    // Review Queue filters
    const rSearch   = document.getElementById('adm-review-search');
    const rPriority = document.getElementById('adm-review-priority-select');
    const rStatus   = document.getElementById('adm-review-status-select');
    const rReset    = document.getElementById('adm-review-reset-btn');

    if (rSearch) rSearch.addEventListener('input', () => {
      clearTimeout(this._reviewSearchTimeout);
      this._reviewSearchTimeout = setTimeout(() => this.loadReviewQueue(), 250);
    });
    if (rPriority) rPriority.addEventListener('change', () => this.loadReviewQueue());
    if (rStatus)   rStatus.addEventListener('change', () => this.loadReviewQueue());
    if (rReset) {
      rReset.addEventListener('click', () => {
        if (rSearch)   rSearch.value = '';
        if (rPriority) rPriority.value = 'all';
        if (rStatus)   rStatus.value = 'all';
        this.loadReviewQueue();
      });
    }

    // Audit Log filters
    const aSearch = document.getElementById('adm-audit-search');
    const aStatus = document.getElementById('adm-audit-status-select');
    const aReset  = document.getElementById('adm-audit-reset-btn');

    if (aSearch) aSearch.addEventListener('input', () => this._filterAndRenderAuditLog());
    if (aStatus) aStatus.addEventListener('change', () => this._filterAndRenderAuditLog());
    if (aReset) {
      aReset.addEventListener('click', () => {
        if (aSearch) aSearch.value = '';
        if (aStatus) aStatus.value = 'all';
        this._filterAndRenderAuditLog();
      });
    }

    // Medical Knowledge Base filters (Debounced API fetch)
    const kSearch   = document.getElementById('adm-kb-search');
    const kCategory = document.getElementById('adm-kb-category-select');
    const kRisk     = document.getElementById('adm-kb-risk-select');
    const kStatus   = document.getElementById('adm-kb-status-select');
    const kReset    = document.getElementById('adm-kb-reset-btn');

    const triggerKbLoad = () => {
      clearTimeout(this._searchTimeout);
      this._searchTimeout = setTimeout(() => this.loadKnowledgeBase(), 300);
    };

    if (kSearch)   kSearch.addEventListener('input', triggerKbLoad);
    if (kCategory) kCategory.addEventListener('change', () => this.loadKnowledgeBase());
    if (kRisk)     kRisk.addEventListener('change', () => this.loadKnowledgeBase());
    if (kStatus)   kStatus.addEventListener('change', () => this.loadKnowledgeBase());
    if (kReset) {
      kReset.addEventListener('click', () => {
        if (kSearch)   kSearch.value = '';
        if (kCategory) kCategory.value = 'all';
        if (kRisk)     kRisk.value = 'all';
        if (kStatus)   kStatus.value = 'all';
        this.loadKnowledgeBase();
      });
    }
  },

  // ── Admin Dashboard Stats ──
  loadDashboard: async function () {
    try {
      const res  = await fetch('/api/admin/stats');
      const data = await res.json();
      if (data.status === 'success') {
        const s = data.stats;
        this._setText('adm-total-users',   s.total_users   ?? '—');
        this._setText('adm-total-scans',   s.total_scans   ?? '—');
        this._setText('adm-pending-review',s.pending_review || '0');
        this._setText('adm-model-status', s.model_status || 'Unavailable');
        this._setText('adm-model-name', s.active_model_name || 'Active model');

        // System health details
        const healthEl = document.getElementById('adm-health-details');
        if (healthEl && s.health) {
          healthEl.innerHTML = Object.entries(s.health).map(([k, v]) => `
            <div class="d-flex justify-content-between align-items-center py-2 border-bottom" style="border-color:var(--border-muted)!important;">
              <span class="small text-muted">${k}</span>
              <span class="badge-pill ${v.ok ? 'badge-emerald' : 'badge-rose'}" style="font-size:.75rem;">${v.label}</span>
            </div>`).join('');
        }

        // Live class distribution chart
        this._renderPredictionChart('adm-class-chart', '_classChart', s.active_model_distribution || []);
      } else {
        Toast.error('Could not load admin stats.', 'Admin');
      }
    } catch (err) {
      console.error('[Admin] Dashboard load error:', err);
    }
  },

  // ── User Management ──
  loadUsers: async function () {
    const tbody = document.getElementById('adm-users-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-center py-5 text-muted"><i class="fa-solid fa-spinner fa-spin me-2"></i>Loading users…</td></tr>`;

    try {
      const res  = await fetch('/api/admin/users');
      const data = await res.json();
      if (data.status === 'success') {
        this._rawUsers = data.users || [];
        this._filterAndRenderUsers();
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-danger">Failed to load users.</td></tr>`;
    }
  },

  _filterAndRenderUsers: function () {
    const tbody = document.getElementById('adm-users-tbody');
    if (!tbody) return;

    const query  = (document.getElementById('adm-users-search')?.value || '').toLowerCase().trim();
    const role   = document.getElementById('adm-users-role-select')?.value || 'all';
    const status = document.getElementById('adm-users-status-select')?.value || 'all';

    let filtered = this._rawUsers.filter(u => {
      // Role filter
      if (role !== 'all' && u.role !== role) return false;
      // Status filter
      if (status === 'active' && u.is_active === false) return false;
      if (status === 'disabled' && u.is_active !== false) return false;
      // Search query
      if (query) {
        const name  = (u.full_name || '').toLowerCase();
        const email = (u.email || '').toLowerCase();
        const id    = String(u.id);
        if (!name.includes(query) && !email.includes(query) && !id.includes(query)) return false;
      }
      return true;
    });

    if (!filtered.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-muted">No matching users found.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(u => {
      const joined = this._formatDate(u.created_at, { year:'numeric', month:'short', day:'numeric' });
      const roleBadge = u.role === 'admin'
        ? `<span class="badge-pill badge-amber" style="font-size:.7rem;">Admin</span>`
        : `<span class="badge-pill badge-teal" style="font-size:.7rem;">Patient</span>`;
      const statusBadge = u.is_active !== false
        ? `<span class="badge-pill badge-emerald" style="font-size:.7rem;">Active</span>`
        : `<span class="badge-pill badge-rose" style="font-size:.7rem;">Disabled</span>`;

      const safeName = (u.full_name || '').replace(/'/g, "\\'");
      const userObjEscaped = JSON.stringify(u).replace(/"/g, '&quot;');

      return `<tr>
        <td class="ps-4">
          <div class="fw-600">${u.full_name || '—'}</div>
          <div class="small text-muted">${statusBadge}</div>
        </td>
        <td class="small text-muted">${u.email}</td>
        <td>${roleBadge}</td>
        <td class="small text-muted">${joined}</td>
        <td class="small">${u.scan_count || 0}</td>
        <td class="text-end pe-4">
          <button class="btn btn-ghost btn-sm text-teal me-1" onclick="AdminModule._openEditUserModal(${userObjEscaped})" title="Edit User Details">
            <i class="fa-solid fa-pen-to-square"></i>
          </button>
          ${u.role !== 'admin' ? `
          <button class="btn btn-ghost btn-sm text-warning me-1" onclick="AdminModule._toggleUser(${u.id}, '${safeName}')" title="${u.is_active !== false ? 'Deactivate Account' : 'Activate Account'}">
            <i class="fa-solid fa-${u.is_active !== false ? 'ban' : 'check'}"></i>
          </button>
          <button class="btn btn-ghost btn-sm text-danger" onclick="AdminModule._deleteUser(${u.id}, '${safeName}')" title="Delete User Account">
            <i class="fa-solid fa-trash"></i>
          </button>` : ''}
        </td>
      </tr>`;
    }).join('');
  },

  _openEditUserModal: function (user) {
    document.getElementById('edit-user-id').value       = user.id;
    document.getElementById('edit-user-name').value     = user.full_name || '';
    document.getElementById('edit-user-email').value    = user.email || '';
    document.getElementById('edit-user-role').value     = user.role || 'patient';
    document.getElementById('edit-user-disabled').value = user.is_active === false ? '1' : '0';

    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('editUserModal'));
    modal.show();
  },

  _saveUser: async function () {
    const userId   = document.getElementById('edit-user-id').value;
    const name     = document.getElementById('edit-user-name').value.trim();
    const email    = document.getElementById('edit-user-email').value.trim();
    const role     = document.getElementById('edit-user-role').value;
    const disabled = document.getElementById('edit-user-disabled').value === '1';
    const btn      = document.getElementById('save-user-submit-btn');

    if (!name || !email) {
      Toast.warning('Name and Email are required.', 'Validation');
      return;
    }

    if (btn) btn.disabled = true;
    try {
      const res  = await fetch(`/api/admin/users/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: name,
          email: email,
          role: role,
          is_active: !disabled
        })
      });
      const data = await res.json();
      if (res.ok && data.status === 'success') {
        Toast.success('User details updated successfully.', 'User Management');
        bootstrap.Modal.getInstance(document.getElementById('editUserModal'))?.hide();
        this.loadUsers();
      } else {
        Toast.error(data.message || 'Failed to update user.', 'Error');
      }
    } catch (err) {
      Toast.error('Server error updating user.', 'Error');
    } finally {
      if (btn) btn.disabled = false;
    }
  },

  _toggleUser: async function (userId, name) {
    if (!confirm(`Toggle active status for ${name}?`)) return;
    try {
      const res  = await fetch(`/api/admin/users/${userId}/toggle-active`, { method: 'POST' });
      const data = await res.json();
      if (data.status === 'success') {
        Toast.success(`${name}'s status updated.`, 'Admin');
        this.loadUsers();
      } else {
        Toast.error(data.message || 'Action failed.', 'Error');
      }
    } catch (err) {
      Toast.error('Server error.', 'Error');
    }
  },

  _deleteUser: async function (userId, name) {
    if (!confirm(`Are you sure you want to permanently delete user "${name}"? This will delete all associated scans and reports. This action cannot be undone.`)) return;
    try {
      const res  = await fetch(`/api/admin/users/${userId}`, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok && data.status === 'success') {
        Toast.success(data.message || `User ${name} deleted successfully.`, 'Admin User Management');
        this.loadUsers();
      } else {
        Toast.error(data.message || 'Failed to delete user.', 'Error');
      }
    } catch (err) {
      Toast.error('Server error deleting user.', 'Error');
    }
  },

  // ── Model Analytics ──
  loadAnalytics: async function () {
    try {
      const res  = await fetch('/api/analytics');
      const data = await res.json();
      if (data.status !== 'success') return;

      const report = data.benchmark_metrics;
      const metrics = report?.overall_metrics;
      this._setText('kpi-accuracy',  metrics ? (metrics.accuracy * 100).toFixed(2) + '%' : 'N/A');
      this._setText('kpi-precision', metrics ? metrics.precision.toFixed(4) : 'N/A');
      this._setText('kpi-recall',    metrics ? metrics.recall.toFixed(4) : 'N/A');
      this._setText('kpi-f1',        metrics ? metrics.f1_score.toFixed(4) : 'N/A');
      this._setText('adm-analytics-model', data.active_model_name || 'Active model');
      document.getElementById('adm-benchmark-unavailable').hidden = Boolean(metrics);
      document.getElementById('adm-benchmark-chart').hidden = !metrics;
      if (metrics) this._renderModelChart(metrics);
      this._renderValidationDetails(report);
      this._renderPredictionChart('adm-dist-chart', '_distChart', data.active_model_distribution || []);
    } catch (err) {
      console.error('[Admin] Analytics load error:', err);
    }
  },

  _renderValidationDetails: function (report) {
    const summary = document.getElementById('adm-validation-summary');
    const metrics = report?.overall_metrics;
    const sampleCount = report?.dataset_info?.total_samples;
    summary.hidden = !metrics;
    if (metrics) {
      summary.textContent = [
        `${sampleCount} validation samples`,
        `Loss ${metrics.validation_loss.toFixed(6)}`,
        `Weighted precision ${metrics.weighted_precision.toFixed(4)}`,
        `Weighted recall ${metrics.weighted_recall.toFixed(4)}`,
        `Weighted F1 ${metrics.weighted_f1_score.toFixed(6)}`
      ].join(' ? ');
    }

    const rows = report?.per_class_metrics || [];
    document.getElementById('adm-class-validation').hidden = rows.length === 0;
    document.getElementById('adm-class-validation-rows').replaceChildren(...rows.map(row => {
      const tr = document.createElement('tr');
      const name = document.createElement('th');
      name.scope = 'row';
      name.textContent = row.name;
      tr.appendChild(name);
      for (const value of [row.precision.toFixed(4), row.recall.toFixed(4), row.f1_score.toFixed(4), row.support]) {
        const cell = tr.insertCell();
        cell.className = 'text-end';
        cell.textContent = value;
      }
      return tr;
    }));
  },

  _renderModelChart: function (metrics) {
    const canvas = document.getElementById('adm-per-class-chart');
    if (!canvas || !window.Chart) return;
    if (this._perClassChart) this._perClassChart.destroy();
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = isDark ? '#8d96a0' : '#475569';
    this._perClassChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: ['Accuracy', 'Macro Precision', 'Macro Recall', 'Macro F1'],
        datasets: [{
          label: 'Score (%)',
          data: [
            +(metrics.accuracy * 100).toFixed(1),
            +(metrics.precision * 100).toFixed(1),
            +(metrics.recall * 100).toFixed(1),
            +(metrics.f1_score * 100).toFixed(1)
          ],
          backgroundColor: [
            'rgba(52,211,153,0.7)',
            'rgba(20,184,166,0.7)',
            'rgba(59,130,246,0.7)',
            'rgba(168,85,247,0.7)'
          ],
          borderRadius: 4
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: { 
          x: { ticks: { color: textColor, font: { size: 13, weight: '600' } } }, 
          y: { min: 0, max: 100, ticks: { color: textColor } } 
        },
        plugins: { legend: { display: false } }
      }
    });
  },

  _renderPredictionChart: function (canvasId, chartKey, rows) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !window.Chart) return;
    if (this[chartKey]) this[chartKey].destroy();
    this[chartKey] = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: rows.map(row => row.name),
        datasets: [{ label: 'Scans', data: rows.map(row => row.count), backgroundColor: '#14b8a6' }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
        plugins: { legend: { display: false } }
      }
    });
  },

  // ── Review Queue ──
  loadReviewQueue: async function (append = false) {
    clearTimeout(this._reviewSearchTimeout);
    const requestId = ++this._reviewPageRequest;
    const cont = document.getElementById('adm-review-queue-container');
    if (!cont) return;
    const params = new URLSearchParams({
      status: document.getElementById('adm-review-status-select')?.value || 'all',
      priority: document.getElementById('adm-review-priority-select')?.value || 'all',
      search: document.getElementById('adm-review-search')?.value.trim() || '',
      limit: '50',
      offset: '0'
    });
    const filterKey = params.toString();
    append = append && filterKey === this._reviewFilterKey;
    params.set('offset', String(append ? this._reviewPage?.next_offset || 0 : 0));
    if (!append) cont.innerHTML = '<div class="text-center py-5 text-muted">Loading review queue...</div>';
    const more = document.getElementById('adm-review-load-more');
    if (more) more.disabled = true;
    try {
      const res = await fetch('/api/review/queue?' + params.toString(), { cache: 'no-store' });
      const data = await res.json();
      if (requestId !== this._reviewPageRequest) return;
      if (!res.ok || data.status !== 'success') throw new Error(data.message);
      this._reviewPage = data;
      this._reviewFilterKey = filterKey;
      const items = data.items || data.queue || [];
      this._rawReviewItems = append ? this._rawReviewItems.concat(items) : items;
      this._filterAndRenderReviewQueue();
    } catch (error) {
      if (requestId !== this._reviewPageRequest) return;
      if (append) {
        if (more) more.disabled = false;
        Toast.error('Could not load more reports. Please try again.', 'Review Queue');
      } else {
        cont.innerHTML = '<div class="card p-4 text-danger text-center">Failed to load review queue. Please refresh.</div>';
      }
    }
  },

  _filterAndRenderReviewQueue: function () {
    const cont = document.getElementById('adm-review-queue-container');
    if (!cont) return;

    const query    = (document.getElementById('adm-review-search')?.value || '').toLowerCase().trim();
    const priority = document.getElementById('adm-review-priority-select')?.value || 'all';
    const status   = document.getElementById('adm-review-status-select')?.value || 'all';

    let filtered = this._rawReviewItems.filter(item => {
      // Priority filter
      if (priority !== 'all' && (item.priority || 'normal').toLowerCase() !== priority) return false;
      // Status filter
      if (status !== 'all' && (item.status || 'pending').toLowerCase() !== status) return false;
      // Search query
      if (query) {
        const cond  = (item.predicted_name || item.assessment?.predicted_name || '').toLowerCase();
        const pat   = (item.patient_name || item.assessment?.patient_name || '').toLowerCase();
        const qid   = String(item.id);
        const scanId = (item.assessment_id || '').toLowerCase();
        if (!cond.includes(query) && !pat.includes(query) && !qid.includes(query) && !scanId.includes(query)) return false;
      }
      return true;
    });

    // Update badge count
    const badge = document.getElementById('review-queue-badge');
    if (badge) {
      badge.textContent = this._reviewPage?.pending_count ?? this._rawReviewItems.filter(i => (i.status || 'pending') === 'pending').length;
      badge.classList.remove('d-none');
    }

    if (!filtered.length) {
      cont.innerHTML = `<div class="card p-5 text-center"><i class="fa-solid fa-circle-info fa-2x text-teal mb-3"></i><p class="text-muted mb-0">No review queue items match the selected filter criteria.</p></div>`;
      return;
    }

    const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);

    cont.innerHTML = filtered.map(item => {
      const dt = this._formatDate(item.assessment_date || item.created_at, { month:'short', day:'numeric', year:'numeric', hour:'2-digit', minute:'2-digit' });
      const itemStatus = item.status || 'pending';
      const statusBadgeClass = itemStatus === 'completed' ? 'badge-emerald' : itemStatus === 'rejected' ? 'badge-rose' : 'badge-amber';
      const priorityBadgeClass = item.priority === 'urgent' ? 'badge-rose' : item.priority === 'high' ? 'badge-amber' : 'badge-teal';

      return `<div class="card p-4 mb-3">
        <div class="d-flex justify-content-between align-items-start flex-wrap gap-2">
          <div>
            <div class="d-flex align-items-center gap-2 mb-1">
              <span class="fw-700 font-outfit text-teal" style="font-size:1.1rem;">${escape(item.predicted_name || 'Unknown Condition')}</span>
              <span class="badge-pill ${statusBadgeClass}" style="font-size:.7rem;">${itemStatus.toUpperCase()}</span>
              <span class="badge-pill ${priorityBadgeClass}" style="font-size:.7rem;">${(item.priority || 'normal').toUpperCase()} PRIORITY</span>
            </div>
            <div class="small text-muted">Patient: <strong>${escape(item.patient_name || 'Anonymous')}</strong> · Submitted: ${dt} · Scan ID: ${escape(item.assessment_id)}</div>
            <div class="small text-muted mt-1">Model: ${item.model_id === 'dataset2-mobilenetv2-keras' ? 'Dataset2 Keras MobileNetV2' : 'Unrecorded'}</div>
            ${item.queue_reason ? `<div class="small text-muted mt-1"><i class="fa-solid fa-circle-exclamation text-amber me-1"></i>Flag Reason: ${escape(item.queue_reason)}</div>` : ''}
            ${item.derm_verdict ? `<div class="small text-emerald mt-2 border-top pt-2" style="border-color:var(--border-muted)!important;"><i class="fa-solid fa-user-doctor me-1"></i>Verdict: <strong>${escape(item.derm_verdict)}</strong> ${item.derm_notes ? `— <em>${escape(item.derm_notes)}</em>` : ''}</div>` : ''}
          </div>
          <div class="d-flex gap-2 align-items-center">
            <button class="btn btn-primary btn-sm" onclick="AdminModule._openVerdictModal(${item.id})">
              <i class="fa-solid fa-stethoscope me-1"></i>${item.derm_verdict ? 'Review Report & Edit Verdict' : 'Review Patient Report'}
            </button>
            <button class="btn btn-ghost btn-sm text-danger" onclick="AdminModule._deleteReviewItem(${item.id})" title="Delete Case from Queue">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </div>
      </div>`;
    }).join('');
    const summary = document.createElement('p');
    summary.className = 'small text-muted mb-3';
    summary.textContent = `Showing ${this._rawReviewItems.length} of ${this._reviewPage?.total_count ?? filtered.length} reports. Newest first.`;
    cont.prepend(summary);
    if (this._reviewPage?.has_more) {
      const more = document.createElement('button');
      more.id = 'adm-review-load-more';
      more.className = 'btn btn-outline mb-4';
      more.textContent = 'Load Older Reports';
      more.addEventListener('click', () => this.loadReviewQueue(true));
      cont.appendChild(more);
    }
  },

  _deleteReviewItem: async function (queueId) {
    if (!confirm('Are you sure you want to remove this item from the review queue?')) return;
    try {
      const res  = await fetch(`/api/review/queue/${queueId}`, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok && data.status === 'success') {
        Toast.success('Review item removed from the queue.', 'Review Queue');
        this.loadReviewQueue();
      } else {
        Toast.error(data.message || 'Failed to delete item.', 'Error');
      }
    } catch (err) {
      Toast.error('Server error deleting review item.', 'Error');
    }
  },

  _updateVerdictAccess: function () {
    const reviewed = Boolean(this._reviewReportToken && document.getElementById('review-report-confirm')?.checked);
    document.getElementById('review-verdict-fields').disabled = !reviewed;
    document.getElementById('submit-verdict-btn').disabled = !reviewed;
  },

  _openVerdictModal: async function (queueId) {
    const requestId = ++this._reviewReportRequest;
    this._reviewReportToken = null;
    const confirm = document.getElementById('review-report-confirm');
    confirm.checked = false;
    confirm.disabled = true;
    document.getElementById('verdict-queue-id').value = '';
    document.getElementById('verdict-diagnosis').value = '';
    document.getElementById('verdict-notes').value = '';
    document.getElementById('verdict-status').value = 'reviewed';
    const report = document.getElementById('review-patient-report');
    report.innerHTML = '<div class="text-muted py-4">Loading patient report...</div>';
    this._updateVerdictAccess();
    bootstrap.Modal.getOrCreateInstance(document.getElementById('verdictModal')).show();

    try {
      const response = await fetch(`/api/review/queue/${encodeURIComponent(queueId)}`);
      const data = await response.json();
      if (requestId !== this._reviewReportRequest) return;
      if (!response.ok || data.status !== 'success' || !data.report || !data.report_review_token) {
        throw new Error(data.message || 'Patient report is unavailable.');
      }
      this._renderReviewReport(data);
      const item = data.item;
      document.getElementById('verdict-queue-id').value = item.id;
      document.getElementById('verdict-diagnosis').value = item.derm_verdict || '';
      document.getElementById('verdict-notes').value = item.derm_notes || '';
      document.getElementById('verdict-status').value = item.verdict_category || 'reviewed';
      this._reviewReportToken = data.report_review_token;
      confirm.disabled = false;
    } catch (error) {
      if (requestId !== this._reviewReportRequest) return;
      report.textContent = error.message || 'Could not load the patient report. Close this window and try again.';
    }
  },

  _renderReviewReport: function (data) {
    const report = data.report;
    const assets = data.report_assets || {};
    const escape = value => String(value ?? 'Not recorded').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);
    const score = value => Number.isFinite(value) ? (value * 100).toFixed(1) + '%' : 'Not recorded';
    const photo = (url, label) => `<div class="col-md-4">
      <div class="small fw-600 mb-2">${label}</div>
      ${url ? `<a href="${escape(url)}" target="_blank" rel="noopener"><img src="${escape(url)}" class="img-fluid rounded border" style="max-height:240px;object-fit:contain;" alt="${label}"></a>`
        : '<p class="small text-muted">Image unavailable for this assessment.</p>'}
    </div>`;
    const symptoms = [
      ['Itching', report.itching, '/10'],
      ['Pain', report.pain, '/10'],
      ['Redness', report.redness, '/10'],
      ['Duration', report.duration_days, ' days'],
      ['Fever', ({0: 'None', 1: 'Mild', 2: 'High'})[report.fever_level], ''],
      ['Burning', ({0: 'None', 1: 'Mild', 2: 'Moderate', 3: 'Severe'})[report.burning_level], ''],
    ];
    const predictions = report.top_predictions || [];
    const factors = report.contributing_factors || [];
    const fuzzy = report.fuzzy_explanation;
    const rules = fuzzy?.activated_rules || [];
    document.getElementById('review-patient-report').innerHTML = `
      <div class="d-flex justify-content-between align-items-start flex-wrap gap-3 mb-3">
        <div>
          <h5 class="fw-700 mb-1">Patient Assessment Report</h5>
          <div>${escape(report.patient_name)} · Age: ${escape(report.patient_age || 'Not recorded')}</div>
          <div class="small text-muted">Scan ID: ${escape(report.id)} · ${escape(this._formatDate(report.created_at))}</div>
          <div class="small text-muted">Body region: ${escape(report.body_region || 'Not recorded')}</div>
        </div>
        <a class="btn btn-outline btn-sm" href="${escape(data.report_download_url)}" target="_blank" rel="noopener">
          <i class="fa-solid fa-file-pdf me-1"></i>Download Full PDF Report
        </a>
      </div>
      <div class="row g-3 mb-4">
        ${photo(assets.image_filename, 'Uploaded skin photo')}
        ${photo(assets.overlay_filename, 'Grad-CAM overlay')}
        ${photo(assets.heatmap_filename, 'Grad-CAM heatmap')}
      </div>
      <div class="p-3 bg-teal-soft rounded mb-3">
        <div class="fw-600">AI prediction: ${escape(report.predicted_name)} · Match score: ${score(report.model_score)}</div>
        <div class="small">Model: ${report.model_id === 'dataset2-mobilenetv2-keras' ? 'Dataset2 Keras MobileNetV2' : 'Unrecorded'}</div>
        <div class="small">Image quality: ${escape(report.quality_status)}</div>
        <div class="small">Severity: ${escape(report.severity_category)} · Score: ${escape(report.severity_score)}/100</div>
      </div>
      <h6 class="fw-700">Assessment Summary</h6>
      <p style="white-space:pre-wrap;">${escape(report.clinical_summary || 'No summary was saved for this assessment.')}</p>
      <h6 class="fw-700">Reported Symptoms</h6>
      <dl class="row mb-3">
        ${symptoms.map(([name, value, unit]) => `<dt class="col-sm-3 small">${name}</dt><dd class="col-sm-3 small">${escape(value)}${value == null ? '' : unit}</dd>`).join('')}
      </dl>
      <h6 class="fw-700">Top Model Matches</h6>
      ${predictions.length ? `<ul>${predictions.map(prediction => `<li>${escape(prediction.name || prediction.code)} · ${score(prediction.score)}</li>`).join('')}</ul>`
        : '<p class="small text-muted">No alternative matches were saved.</p>'}
      <h6 class="fw-700">Severity Explanation</h6>
      ${factors.length ? `<ul>${factors.map(factor => `<li>${escape(factor)}</li>`).join('')}</ul>` : ''}
      ${rules.length ? `<details class="mb-3"><summary>View activated fuzzy rules</summary><ul class="small mt-2">
        ${rules.map(rule => `<li>${escape(rule.condition)} · ${escape(rule.consequent)} · Activation: ${escape(rule.firing_strength)}</li>`).join('')}
      </ul></details>` : '<p class="small text-muted">A detailed fuzzy rule explanation was not saved.</p>'}
      <p class="small text-muted mb-0">The AI prediction and symptom score support your review. Enter your clinical assessment below.</p>
    `;
  },

  _submitVerdict: async function () {
    const queueId    = document.getElementById('verdict-queue-id')?.value;
    const diagnosis  = document.getElementById('verdict-diagnosis')?.value.trim();
    const notes      = document.getElementById('verdict-notes')?.value.trim();
    const verdictCat = document.getElementById('verdict-status')?.value || 'reviewed';
    const btn        = document.getElementById('submit-verdict-btn');

    if (!this._reviewReportToken || !document.getElementById('review-report-confirm')?.checked) {
      Toast.warning('Review the patient report and confirm before entering a verdict.', 'Report Required');
      return;
    }
    if (!queueId) { Toast.warning('Invalid review item ID.', 'Validation'); return; }
    if (!diagnosis) { Toast.warning('Please enter a clinical diagnosis / verdict.', 'Validation'); return; }

    if (btn) btn.disabled = true;
    try {
      const res  = await fetch(`/api/review/queue/${encodeURIComponent(queueId)}/verdict`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          report_review_token: this._reviewReportToken,
          report_reviewed: true,
          diagnosis: diagnosis,
          verdict_category: verdictCat,
          notes: notes,
          status: 'completed'
        })
      });
      const data = await res.json();
      if (res.ok && data.status === 'success') {
        Toast.success(data.message || 'Verdict submitted successfully.', 'Admin Verdict');
        const modalEl = document.getElementById('verdictModal');
        if (modalEl) {
          const bsModal = bootstrap.Modal.getInstance(modalEl);
          if (bsModal) bsModal.hide();
        }
        if (typeof this.loadReviewQueue === 'function') {
          this.loadReviewQueue();
        }
      } else {
        Toast.error(data.message || data.error || 'Failed to submit verdict.', 'Verdict Error');
      }
    } catch (err) {
      console.error('[Admin] Error submitting verdict:', err);
      Toast.error(err.message || 'Server error while submitting verdict.', 'Connection Error');
    } finally {
      this._updateVerdictAccess();
    }
  },

  // ── Audit Log ──
  loadAuditLog: async function () {
    const tbody = document.getElementById('adm-audit-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted"><i class="fa-solid fa-spinner fa-spin me-2"></i>Loading audit log…</td></tr>`;

    try {
      const res  = await fetch('/api/auth/audit-log?limit=100');
      const data = await res.json();
      if (data.status === 'success') {
        this._rawAuditLogs = data.logs || [];
        this._filterAndRenderAuditLog();
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">Failed to load audit log.</td></tr>`;
    }
  },

  _filterAndRenderAuditLog: function () {
    const tbody = document.getElementById('adm-audit-tbody');
    if (!tbody) return;

    const query  = (document.getElementById('adm-audit-search')?.value || '').toLowerCase().trim();
    const status = document.getElementById('adm-audit-status-select')?.value || 'all';

    let filtered = this._rawAuditLogs.filter(log => {
      // Outcome status filter
      if (status === 'success' && log.status === 'failed') return false;
      if (status === 'failed' && log.status !== 'failed') return false;
      // Search query
      if (query) {
        const user = (log.user_email || '').toLowerCase();
        const act  = (log.action || '').toLowerCase();
        const res  = (log.resource || '').toLowerCase();
        const ip   = (log.ip_address || '').toLowerCase();
        if (!user.includes(query) && !act.includes(query) && !res.includes(query) && !ip.includes(query)) return false;
      }
      return true;
    });

    if (!filtered.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">No audit log entries match filter criteria.</td></tr>`;
      return;
    }

    const actionColors = {
      login: 'badge-emerald', logout: 'badge-neutral',
      login_failed: 'badge-rose', admin_login: 'badge-amber',
      register: 'badge-teal', password_reset: 'badge-blue',
      password_changed: 'badge-blue', assessment_create: 'badge-teal',
      report_downloaded: 'badge-neutral', profile_updated: 'badge-neutral'
    };

    tbody.innerHTML = filtered.map(log => {
      const dt  = this._formatDate(log.timestamp, { month:'short', day:'numeric', year:'numeric', hour:'2-digit', minute:'2-digit' });
      const ac  = log.action || '—';
      const cls = actionColors[ac] || 'badge-neutral';
      return `<tr>
        <td class="ps-4 small text-muted">${dt}</td>
        <td class="small">${log.user_email || '—'}</td>
        <td><span class="badge-pill ${cls}" style="font-size:.7rem;">${ac}</span></td>
        <td class="small text-muted">${log.ip_address || '—'}</td>
        <td class="small text-muted pe-4">${log.status === 'failed' ? '<span class="text-danger fw-600">Failed</span>' : (log.resource || '—')}</td>
      </tr>`;
    }).join('');
  },

  // ── Medical Content Management (Req 30) ──
  loadKnowledgeBase: async function () {
    const tbody = document.getElementById('adm-knowledge-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted"><i class="fa-solid fa-spinner fa-spin me-2"></i>Loading medical knowledge base…</td></tr>`;

    const search   = document.getElementById('adm-kb-search')?.value.trim() || '';
    const category = document.getElementById('adm-kb-category-select')?.value || 'all';
    const risk     = document.getElementById('adm-kb-risk-select')?.value || 'all';
    const status   = document.getElementById('adm-kb-status-select')?.value || 'all';

    const params = new URLSearchParams();
    if (search)   params.append('search', search);
    if (category) params.append('category', category);
    if (risk)     params.append('risk_level', risk);
    if (status)   params.append('status', status);

    try {
      const res  = await fetch(`/api/admin/knowledge-base?${params.toString()}`);
      const data = await res.json();
      if (data.status === 'success' && tbody) {
        const items = data.items || [];
        if (!items.length) {
          tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">No knowledge base entries found matching search criteria.</td></tr>`;
          return;
        }
        tbody.innerHTML = items.map(item => {
          const riskBadge = item.risk_level === 'High' ? 'badge-rose' : item.risk_level === 'Moderate' ? 'badge-amber' : 'badge-emerald';
          const statusBadge = item.status === 'approved' ? 'badge-emerald' : item.status === 'draft' ? 'badge-amber' : 'badge-neutral';
          return `<tr>
            <td class="ps-4 fw-700 text-teal">${item.condition_code.toUpperCase()}</td>
            <td><div class="fw-600">${item.condition_name}</div></td>
            <td class="small text-muted">${item.category}</td>
            <td><span class="badge-pill ${riskBadge}" style="font-size:.7rem;">${item.risk_level}</span></td>
            <td class="small text-muted">v${item.version || '1.0'}</td>
            <td class="small text-muted">${item.last_reviewed || '2026-10-01'}</td>
            <td><span class="badge-pill ${statusBadge}" style="font-size:.7rem;">${item.status || 'approved'}</span></td>
            <td class="text-end pe-4">
              <button class="btn btn-ghost btn-sm text-teal me-1" onclick="AdminModule._openEditKbModal('${item.condition_code}')" title="Edit Medical Guidance">
                <i class="fa-solid fa-pen-to-square me-1"></i>Edit
              </button>
              <button class="btn btn-ghost btn-sm text-danger" onclick="AdminModule._deleteKbItem('${item.condition_code}', '${(item.condition_name || '').replace(/'/g, "\\'")}')" title="Delete Medical Record">
                <i class="fa-solid fa-trash"></i>
              </button>
            </td>
          </tr>`;
        }).join('');
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-danger">Failed to load medical knowledge base.</td></tr>`;
    }
  },

  _createKnowledgeBaseItem: async function () {
    const code = document.getElementById('add-kb-code').value.trim().toLowerCase();
    const name = document.getElementById('add-kb-name').value.trim();
    const btn  = document.getElementById('create-kb-submit-btn');

    if (!code || !name) {
      Toast.warning('Condition Code and Name are required.', 'Validation');
      return;
    }

    const splitLines = val => (val || '').split('\n').map(s => s.trim()).filter(s => s.length > 0);

    const payload = {
      condition_code:       code,
      condition_name:       name,
      category:             document.getElementById('add-kb-category').value,
      risk_level:           document.getElementById('add-kb-risk').value,
      description:          document.getElementById('add-kb-desc').value.trim(),
      supportive_care:      splitLines(document.getElementById('add-kb-supportive').value),
      preventive_measures:  splitLines(document.getElementById('add-kb-preventive').value),
      things_to_avoid:      splitLines(document.getElementById('add-kb-avoid').value),
      when_to_see_doctor:   splitLines(document.getElementById('add-kb-doctor').value),
      urgent_warning_signs: splitLines(document.getElementById('add-kb-urgent').value),
      version:              document.getElementById('add-kb-version').value.trim() || '1.0',
      last_reviewed:        new Date().toISOString().split('T')[0],
      status:               document.getElementById('add-kb-status').value
    };

    if (btn) btn.disabled = true;

    try {
      const res  = await fetch('/api/admin/knowledge-base', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (res.ok && data.status === 'success') {
        Toast.success(`Medical condition "${name}" added successfully.`, 'Medical Content');
        bootstrap.Modal.getInstance(document.getElementById('addKnowledgeModal'))?.hide();
        document.getElementById('add-kb-form').reset();
        this.loadKnowledgeBase();
      } else {
        Toast.error(data.message || 'Failed to create record.', 'Error');
      }
    } catch (err) {
      Toast.error('Server connection error.', 'Error');
    } finally {
      if (btn) btn.disabled = false;
    }
  },

  _openEditKbModal: async function (code) {
    try {
      const res  = await fetch(`/api/admin/knowledge-base/${code}`);
      const data = await res.json();
      if (data.status === 'success' && data.item) {
        const item = data.item;
        document.getElementById('edit-kb-code').value          = item.condition_code;
        document.getElementById('edit-kb-code-display').value  = item.condition_code.toUpperCase();
        document.getElementById('edit-kb-name').value          = item.condition_name;
        document.getElementById('edit-kb-desc').value          = item.description || '';
        document.getElementById('edit-kb-supportive').value    = (item.supportive_care || []).join('\n');
        document.getElementById('edit-kb-preventive').value    = (item.preventive_measures || []).join('\n');
        document.getElementById('edit-kb-avoid').value         = (item.things_to_avoid || []).join('\n');
        document.getElementById('edit-kb-doctor').value        = (item.when_to_see_doctor || []).join('\n');
        document.getElementById('edit-kb-urgent').value        = (item.urgent_warning_signs || []).join('\n');
        document.getElementById('edit-kb-version').value       = item.version || '1.0';
        document.getElementById('edit-kb-status').value        = item.status || 'approved';

        const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('editKnowledgeModal'));
        modal.show();
      } else {
        Toast.error('Could not fetch condition entry.', 'Error');
      }
    } catch (err) {
      Toast.error('Failed to load entry details: ' + err.message, 'Error');
    }
  },

  _saveKnowledgeBaseItem: async function () {
    const code = document.getElementById('edit-kb-code').value;
    const btn  = document.getElementById('save-kb-btn');

    const splitLines = val => (val || '').split('\n').map(s => s.trim()).filter(s => s.length > 0);

    const payload = {
      description:          document.getElementById('edit-kb-desc').value.trim(),
      supportive_care:      splitLines(document.getElementById('edit-kb-supportive').value),
      preventive_measures:  splitLines(document.getElementById('edit-kb-preventive').value),
      things_to_avoid:      splitLines(document.getElementById('edit-kb-avoid').value),
      when_to_see_doctor:   splitLines(document.getElementById('edit-kb-doctor').value),
      urgent_warning_signs: splitLines(document.getElementById('edit-kb-urgent').value),
      version:              document.getElementById('edit-kb-version').value.trim() || '1.0',
      last_reviewed:        new Date().toISOString().split('T')[0],
      status:               document.getElementById('edit-kb-status').value
    };

    if (btn) btn.disabled = true;

    try {
      const res  = await fetch(`/api/admin/knowledge-base/${code}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (data.status === 'success') {
        Toast.success(`Medical content for ${code.toUpperCase()} saved.`, 'Admin Content Management');
        bootstrap.Modal.getInstance(document.getElementById('editKnowledgeModal'))?.hide();
        this.loadKnowledgeBase();
      } else {
        Toast.error(data.message || 'Update failed.', 'Error');
      }
    } catch (err) {
      Toast.error('Server connection error.', 'Error');
    } finally {
      if (btn) btn.disabled = false;
    }
  },

  _deleteKbItem: async function (code, name) {
    if (!confirm(`Are you sure you want to delete medical condition "${name}" (${code.toUpperCase()}) from the knowledge base?`)) return;
    try {
      const res  = await fetch(`/api/admin/knowledge-base/${code}`, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok && data.status === 'success') {
        Toast.success(`Medical condition "${name}" deleted successfully.`, 'Medical Content');
        this.loadKnowledgeBase();
      } else {
        Toast.error(data.message || 'Failed to delete record.', 'Error');
      }
    } catch (err) {
      Toast.error('Server error deleting record.', 'Error');
    }
  },

  _setText: function (id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  },

  _formatDate: function (str, options) {
    if (!str) return '—';
    const cleanStr = String(str).trim();
    if (!cleanStr) return '—';
    const safeStr = cleanStr.replace(/-/g, '/').replace('T', ' ');
    const d = new Date(safeStr);
    if (isNaN(d.getTime())) return cleanStr;
    return d.toLocaleString('en-US', options || { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
};

document.addEventListener('DOMContentLoaded', () => {
  AdminModule.init();
});
