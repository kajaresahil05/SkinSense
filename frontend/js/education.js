/**
 * SkinSense — Education Module v2.0
 * Loads condition library from /api/conditions,
 * renders search/filter, and condition detail cards.
 */
window.EducationModule = {
  _conditions: [],

  init: function () {
    window.SectionHooks['education'] = () => this.load();
    this._bindControls();
    window.addEventListener('languageChanged', () => this.load());
  },

  _bindControls: function () {
    const search = document.getElementById('edu-search');
    if (search) search.addEventListener('input', debounce(() => this._filterAndRender(), 300));

    const filterType = document.getElementById('edu-filter-type');
    if (filterType) filterType.addEventListener('change', () => this._filterAndRender());

    const categoryBtns = document.querySelectorAll('.edu-category-btn');
    categoryBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        categoryBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this._filterAndRender();
      });
    });
  },

  load: async function () {
    const grid = document.getElementById('edu-conditions-grid');
    if (grid) grid.innerHTML = `<div class="text-center py-5 text-muted w-100"><i class="fa-solid fa-spinner fa-spin me-2"></i>Loading condition library…</div>`;

    const lang = window.I18nModule ? window.I18nModule.currentLang : 'en';

    try {
      const res  = await fetch(`/api/conditions?lang=${lang}`);
      const data = await res.json();
      if (data.status === 'success') {
        this._conditions = data.conditions || [];
        this._filterAndRender();
      } else {
        this._renderFallback();
      }
    } catch (err) {
      this._renderFallback();
    }
  },

  _filterAndRender: function () {
    const searchVal = (document.getElementById('edu-search')?.value || '').toLowerCase();
    const selectCategory = (document.getElementById('edu-filter-type')?.value || 'all').toLowerCase();
    const btnCategory    = (document.querySelector('.edu-category-btn.active')?.getAttribute('data-category') || 'all').toLowerCase();
    const activeCategory = selectCategory !== 'all' ? selectCategory : btnCategory;

    let filtered = this._conditions;
    if (searchVal) {
      filtered = filtered.filter(c =>
        c.name?.toLowerCase().includes(searchVal) ||
        c.description?.toLowerCase().includes(searchVal) ||
        c.category?.toLowerCase().includes(searchVal)
      );
    }
    if (activeCategory !== 'all') {
      filtered = filtered.filter(c => c.category?.toLowerCase() === activeCategory);
    }

    this._renderGrid(filtered);
  },

  _renderGrid: function (conditions) {
    const grid = document.getElementById('edu-conditions-grid');
    if (!grid) return;
    if (!conditions.length) {
      grid.innerHTML = `<div class="text-center py-5 text-muted w-100"><i class="fa-solid fa-magnifying-glass me-2"></i>No conditions match your search.</div>`;
      return;
    }

    const riskColors = {
      Low:      { bg: 'var(--emerald-50)', border: 'var(--emerald-500)', text: 'var(--emerald-700)' },
      Moderate: { bg: 'var(--amber-50)',   border: 'var(--amber-500)',   text: 'var(--amber-700)' },
      High:     { bg: 'var(--rose-50)',     border: 'var(--rose-500)',     text: 'var(--rose-700)' },
    };

    const t = window.I18nModule ? window.I18nModule.t.bind(window.I18nModule) : (k => k);

    grid.innerHTML = conditions.map(c => {
      const risk = c.risk_level || 'Low';
      const col  = riskColors[risk] || riskColors.Low;
      const learnMoreText = t('learn_more') || 'Learn More';
      return `<div class="col-md-6 col-lg-4">
        <div class="card p-4 h-100" style="border-top:3px solid ${col.border};cursor:pointer;" onclick="EducationModule.showDetail('${c.class_id || c.id}')">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <h6 class="fw-700 mb-0">${c.name}</h6>
            <span class="badge-pill" style="background:${col.bg};color:${col.text};font-size:.7rem;">${risk} Risk</span>
          </div>
          <div class="small text-muted mb-3">${c.category || ''}</div>
          <p class="small text-secondary mb-3">${(c.description || '').substring(0, 120)}${c.description?.length > 120 ? '…' : ''}</p>
          <div class="mt-auto">
            <button class="btn btn-ghost btn-sm w-100" onclick="EducationModule.showDetail('${c.class_id || c.id}')">
              ${learnMoreText} <i class="fa-solid fa-chevron-right ms-1"></i>
            </button>
          </div>
        </div>
      </div>`;
    }).join('');
  },

  showDetail: async function (classId) {
    const detailEl = document.getElementById('edu-detail-panel');
    const gridEl   = document.getElementById('edu-conditions-grid-wrapper');

    if (detailEl) detailEl.classList.remove('d-none');
    if (gridEl)   gridEl.classList.add('d-none');
    if (detailEl) detailEl.innerHTML = `<div class="text-center py-5 text-muted"><i class="fa-solid fa-spinner fa-spin me-2"></i>Loading condition details…</div>`;

    const lang = window.I18nModule ? window.I18nModule.currentLang : 'en';

    try {
      const res  = await fetch(`/api/conditions/${classId}?lang=${lang}`);
      const data = await res.json();
      if (data.status !== 'success') { this._hideDetail(); Toast.error('Could not load condition details.', 'Error'); return; }

      const c    = data.condition;
      const risk = c.risk_level || 'Low';
      const riskBadge = {
        Low:      'badge-emerald',
        Moderate: 'badge-amber',
        High:     'badge-rose'
      }[risk] || 'badge-teal';

      detailEl.innerHTML = `
        <button class="btn btn-ghost btn-sm mb-4" onclick="EducationModule._hideDetail()">
          <i class="fa-solid fa-arrow-left me-1"></i>Back to Library
        </button>
        <div class="card p-4 mb-4">
          <div class="d-flex justify-content-between align-items-start mb-3">
            <div>
              <h3 class="fw-700 mb-1">${c.name}</h3>
              <div class="text-muted small">${c.category || ''}</div>
            </div>
            <div class="d-flex flex-column gap-2 align-items-end">
              <span class="badge-pill ${riskBadge}">${risk} Risk</span>
              ${c.prevalence ? `<span class="badge-pill badge-neutral" style="font-size:.7rem;">Prevalence: ${c.prevalence}</span>` : ''}
            </div>
          </div>
          <p class="text-secondary mb-4">${c.description || ''}</p>

          ${c.symptoms?.length ? `
          <h6 class="fw-700 mb-2"><i class="fa-solid fa-circle-exclamation text-amber me-2"></i>Common Symptoms</h6>
          <div class="d-flex flex-wrap gap-2 mb-4">
            ${c.symptoms.map(s => `<span class="badge-pill badge-neutral" style="font-size:.75rem;">${s}</span>`).join('')}
          </div>` : ''}

          ${c.common_locations?.length ? `
          <h6 class="fw-700 mb-2"><i class="fa-solid fa-location-dot text-teal me-2"></i>Common Locations</h6>
          <div class="d-flex flex-wrap gap-2 mb-4">
            ${c.common_locations.map(l => `<span class="badge-pill badge-teal" style="font-size:.75rem;">${l}</span>`).join('')}
          </div>` : ''}

          ${c.treatment_options?.length ? `
          <h6 class="fw-700 mb-2"><i class="fa-solid fa-pills text-blue me-2"></i>Treatment Options</h6>
          <ul class="small text-secondary mb-4">
            ${c.treatment_options.map(t => `<li>${t}</li>`).join('')}
          </ul>` : ''}

          ${c.recommendation ? `
          <div class="alert-inline info">
            <i class="fa-solid fa-circle-info"></i>
            <div class="small"><strong>Clinical Note:</strong> ${c.recommendation}</div>
          </div>` : ''}

          <div class="alert-inline warning mt-3">
            <i class="fa-solid fa-triangle-exclamation"></i>
            <div class="small">This information is for educational purposes only. Always consult a qualified dermatologist for diagnosis and treatment.</div>
          </div>
        </div>`;
    } catch (err) {
      this._hideDetail();
      Toast.error('Error loading condition details.', 'Error');
    }
  },

  _hideDetail: function () {
    const detailEl = document.getElementById('edu-detail-panel');
    const gridEl   = document.getElementById('edu-conditions-grid-wrapper');
    if (detailEl) detailEl.classList.add('d-none');
    if (gridEl)   gridEl.classList.remove('d-none');
  },

  _renderFallback: function () {
    // Render static HAM10000 conditions as fallback
    const fallback = [
      { id: 'mel',  name: 'Melanoma',             category: 'Malignant',  risk_level: 'High',     description: 'The most dangerous form of skin cancer, developing from melanin-producing cells.' },
      { id: 'nv',   name: 'Melanocytic Nevi',      category: 'Benign',     risk_level: 'Low',      description: 'Common moles. Usually benign but should be monitored for changes.' },
      { id: 'bcc',  name: 'Basal Cell Carcinoma',  category: 'Malignant',  risk_level: 'High',     description: 'Most common skin cancer, arising in basal cells. Rarely metastasizes.' },
      { id: 'akiec',name: 'Actinic Keratosis',     category: 'Pre-cancer', risk_level: 'Moderate', description: 'Rough, scaly patches caused by years of sun exposure. May develop into cancer.' },
      { id: 'bkl',  name: 'Benign Keratosis',      category: 'Benign',     risk_level: 'Low',      description: 'Non-cancerous lesions including solar lentigo and seborrheic keratosis.' },
      { id: 'df',   name: 'Dermatofibroma',        category: 'Benign',     risk_level: 'Low',      description: 'Common benign fibrous nodules of the dermis, usually in the lower legs.' },
      { id: 'vasc', name: 'Vascular Lesions',      category: 'Vascular',   risk_level: 'Moderate', description: 'Angiomas, angiokeratomas, pyogenic granulomas, and hemorrhage.' },
    ];
    this._conditions = fallback;
    this._filterAndRender();
  }
};

document.addEventListener('DOMContentLoaded', () => {
  EducationModule.init();
});
