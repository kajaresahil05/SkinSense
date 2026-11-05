/**
 * SkinSense — Skin Scanner Module v2.0 (Complete Rewrite)
 * Fixes:
 *  - Aligns with new multi-step wizard HTML IDs (scan-dropzone, scan-file-input, etc.)
 *  - Properly shows/hides step panels
 *  - Fixes result element IDs (res-predicted-name, res-top3-list, etc.)
 *  - Wires PDF download and Add-to-Track buttons
 *  - Real camera capture via getUserMedia
 *  - Proper XAI opacity slider
 *  - Gradient-severity badge mapping
 */

// ── Module State ──
let _scanFile = null;
let _scanDataUrl = null;   // local data:URL for immediate display
let _lastAsmId = null;
let _currentAsm = null;
let _currentLang = 'en';

document.addEventListener('DOMContentLoaded', () => {
  ScannerModule.init();
});

window.ScannerModule = {
  _scanTrack: null,
  _linkedTrackId: null,

  setTrack: function (track) {
    this._scanTrack = track;
    this._setText('scan-track-name', track?.track_name || '');
    document.getElementById('scan-track-context')?.classList.toggle('d-none', !track);
    const region = document.getElementById('input-location');
    if (region) region.value = track?.body_region || '';
  },
  init: function () {
    this._bindDropzone();
    this._bindSliders();
    this._bindStepButtons();
    this._bindCamera();
    this._bindResultButtons();
    this._bindXaiSlider();
    this._bindLanguageSelector();
    this._bindQuestionnaire();
    window.SectionHooks['scanner'] = () => ScannerModule.reset();
  },

  // ── Dropzone ──
  _bindDropzone: function () {
    const dropzone  = document.getElementById('scan-dropzone');
    const fileInput = document.getElementById('scan-file-input');
    const removeBtn = document.getElementById('scan-remove-img');

    if (!dropzone || !fileInput) return;

    dropzone.addEventListener('click', e => {
      if (e.target.tagName !== 'BUTTON') fileInput.click();
    });

    dropzone.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
    });

    ['dragenter','dragover','dragleave','drop'].forEach(ev =>
      dropzone.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); }));
    ['dragenter','dragover'].forEach(ev =>
      dropzone.addEventListener(ev, () => dropzone.classList.add('dragover')));
    ['dragleave','drop'].forEach(ev =>
      dropzone.addEventListener(ev, () => dropzone.classList.remove('dragover')));
    dropzone.addEventListener('drop', e => {
      const f = e.dataTransfer?.files?.[0];
      if (f) this._handleFile(f);
    });

    fileInput.addEventListener('change', e => {
      const f = e.target.files?.[0];
      if (f) this._handleFile(f);
    });

    if (removeBtn) removeBtn.addEventListener('click', () => this._clearImage());
  },

  _handleFile: function (file) {
    if (!file.type.match(/^image\/(jpeg|png|webp)$/)) {
      Toast.error('Please select a JPG, PNG, or WEBP image file.', 'Invalid File');
      return;
    }
    if (file.size > 16 * 1024 * 1024) {
      Toast.error('Image size must be under 16 MB.', 'File Too Large');
      return;
    }
    document.getElementById('scan-screening-consent').checked = false;
    _scanFile = file;
    const reader = new FileReader();
    reader.onload = e => {
      _scanDataUrl = e.target.result;  // store for results display
      const preview = document.getElementById('scan-preview-img');
      if (preview) preview.src = _scanDataUrl;
      document.getElementById('scan-dropzone')?.classList.add('d-none');
      document.getElementById('scan-preview-container')?.classList.remove('d-none');
      const nextBtn = document.getElementById('step1-next-btn');
      if (nextBtn) nextBtn.disabled = false;
    };
    reader.readAsDataURL(file);
  },

  _clearImage: function () {
    document.getElementById('scan-screening-consent').checked = false;
    _scanFile = null;
    _scanDataUrl = null;
    const fi = document.getElementById('scan-file-input');
    if (fi) fi.value = '';
    document.getElementById('scan-preview-container')?.classList.add('d-none');
    document.getElementById('scan-dropzone')?.classList.remove('d-none');
    const nextBtn = document.getElementById('step1-next-btn');
    if (nextBtn) nextBtn.disabled = true;
  },

  // ── Symptom sliders ──
  _bindSliders: function () {
    ['itching', 'pain', 'redness'].forEach(id => {
      const input = document.getElementById('input-' + id);
      const label = document.getElementById('val-' + id);
      if (input && label) {
        input.addEventListener('input', () => { label.textContent = `${input.value} / 10`; });
      }
    });
  },

  // ── Step navigation ──
  _bindStepButtons: function () {
    const nextBtn    = document.getElementById('step1-next-btn');
    const backBtn    = document.getElementById('step2-back-btn');
    const analyzeBtn = document.getElementById('step2-analyze-btn');

    const goStep = (showId, hideIds) => {
      hideIds.forEach(id => { const el = document.getElementById(id); if (el) el.classList.add('d-none'); });
      const showEl = document.getElementById(showId);
      if (showEl) showEl.classList.remove('d-none');
    };

    const updateStepIndicator = (active) => {
      for (let i = 1; i <= 3; i++) {
        const circle = document.getElementById(`step-circle-${i}`);
        const label  = document.getElementById(`step-label-${i}`);
        const done   = i < active;
        const cur    = i === active;
        if (circle) {
          circle.classList.toggle('active', cur || done);
          circle.classList.toggle('done', done);
          if (done) circle.innerHTML = '<i class="fa-solid fa-check"></i>';
          else circle.textContent = i;
        }
        if (label) label.classList.toggle('active', cur || done);
      }
      const line12 = document.getElementById('step-line-12');
      const line23 = document.getElementById('step-line-23');
      if (line12) line12.classList.toggle('active', active >= 2);
      if (line23) line23.classList.toggle('active', active >= 3);
    };

    if (nextBtn) {
      nextBtn.addEventListener('click', () => {
        if (!_scanFile) { Toast.warning('Please upload a skin photo first.'); return; }
        goStep('scanner-step-2', ['scanner-step-1']);
        updateStepIndicator(2);
      });
    }

    if (backBtn) {
      backBtn.addEventListener('click', () => {
        goStep('scanner-step-1', ['scanner-step-2']);
        updateStepIndicator(1);
      });
    }

    if (analyzeBtn) {
      analyzeBtn.addEventListener('click', () => {
        if (!_scanFile) { Toast.warning('Please upload a skin photo first.'); return; }
        if (!document.getElementById('scan-screening-consent')?.checked) {
          Toast.warning('Please allow the skin-photo suitability check before running an assessment.');
          return;
        }
        goStep('scanner-step-loading', ['scanner-step-2']);
        updateStepIndicator(3);
        this.runAnalysis();
      });
    }
  },

  // ── Camera capture ──
  _bindCamera: function () {
    const btn = document.getElementById('scan-camera-btn');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        Toast.warning('Camera access not supported on this device or browser.', 'Camera Unavailable');
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
        const modal = document.createElement('div');
        modal.id = 'camera-capture-modal';
        modal.style.cssText = 'position:fixed;inset:0;z-index:9999;background:#000;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1rem;';
        modal.innerHTML = `
          <video id="cam-video" autoplay playsinline style="max-height:70vh;max-width:90vw;border-radius:12px;"></video>
          <div style="display:flex;gap:1rem;">
            <button id="cam-capture-btn" style="padding:.75rem 2rem;background:var(--teal-600);color:#fff;border:none;border-radius:999px;font-weight:700;cursor:pointer;font-size:1rem;">
              <i class="fa-solid fa-camera me-2"></i>Capture
            </button>
            <button id="cam-cancel-btn" style="padding:.75rem 2rem;background:#334155;color:#fff;border:none;border-radius:999px;cursor:pointer;">Cancel</button>
          </div>`;
        document.body.appendChild(modal);
        const video = document.getElementById('cam-video');
        video.srcObject = stream;

        document.getElementById('cam-cancel-btn').addEventListener('click', () => {
          stream.getTracks().forEach(t => t.stop());
          modal.remove();
        });

        document.getElementById('cam-capture-btn').addEventListener('click', () => {
          const canvas = document.createElement('canvas');
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          canvas.getContext('2d').drawImage(video, 0, 0);
          canvas.toBlob(blob => {
            const file = new File([blob], 'camera-capture.jpg', { type: 'image/jpeg' });
            this._handleFile(file);
            stream.getTracks().forEach(t => t.stop());
            modal.remove();
          }, 'image/jpeg', 0.92);
        });
      } catch (err) {
        Toast.error('Could not access camera: ' + err.message, 'Camera Error');
      }
    });
  },

  // ── Run Assessment ──
  runAnalysis: async function () {
    if (!_scanFile) return;

    const track = this._scanTrack;
    const scanFile = _scanFile;
    const formData = new FormData();
    formData.append('image', _scanFile);
    formData.append('image_screening_consent', String(document.getElementById('scan-screening-consent')?.checked === true));
    formData.append('itching',       document.getElementById('input-itching')?.value   || 0);
    formData.append('pain',          document.getElementById('input-pain')?.value       || 0);
    formData.append('redness',       document.getElementById('input-redness')?.value    || 0);
    formData.append('duration_days', document.getElementById('input-duration')?.value   || 1);
    formData.append('fever_level',   document.getElementById('input-fever')?.value      || 0);
    formData.append('burning_level', document.getElementById('input-burning')?.value    || 0);
    formData.append('body_region',   document.getElementById('input-location')?.value   || '');
    formData.append('patient_name',  window.Auth?.currentUser?.full_name || 'Self Assessment');
    formData.append('lang',          window.I18nModule ? window.I18nModule.currentLang : (_currentLang || 'en'));

    try {
      const res  = await fetch('/api/predict', { method: 'POST', body: formData });
      const data = await res.json();
      let linked = false;
      if (track && data.status === 'success' && data.assessment?.id) {
        try {
          await TrackingModule.linkAssessment(track.id, data.assessment.id);
          linked = true;
          Toast.success('Scan added to the lesion timeline.', 'Tracking');
        } catch (error) {
          Toast.warning('Scan saved. Use Add to Lesion Track to retry the link.', 'Tracking');
        }
      }
      if (scanFile !== _scanFile) return;

      document.getElementById('scanner-step-loading')?.classList.add('d-none');

      if (data.status === 'success' && data.assessment) {
        this.setTrack(null);
        this._linkedTrackId = linked ? track.id : null;
        document.getElementById('res-view-track-btn')?.classList.toggle('d-none', !linked);
        _lastAsmId = data.assessment.id;
        _currentAsm = data.assessment;
        this.displayResults(data.assessment);
        document.getElementById('scan-results-section')?.classList.remove('d-none');
        document.getElementById('scan-results-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else {
        document.getElementById('scanner-step-2')?.classList.remove('d-none');
        if (data.error_code === 'image_not_suitable') {
          this._clearImage();
          document.getElementById('step2-back-btn')?.click();
          Toast.show(
            'This is not a valid skin image for assessment. Please upload a clear, close-up photo of the affected skin area.',
            'warning',
            'Invalid Skin Image',
            8000
          );
          return;
        }
        Toast.error(data.message || 'Assessment failed. Please try again.', 'Analysis Error');
      }
    } catch (err) {
      if (scanFile !== _scanFile) return;
      document.getElementById('scanner-step-loading')?.classList.add('d-none');
      document.getElementById('scanner-step-2')?.classList.remove('d-none');
      Toast.error('Server connection error: ' + err.message, 'Network Error');
    }
  },

  // ── Display Results ──
  displayResults: function (asm) {
    _currentAsm = asm;
    const step1 = asm.decision_chain?.step1_image_analysis || {};
    const step3 = asm.decision_chain?.step3_fuzzy_severity || asm.decision_chain?.step4_fuzzy_severity || {};

    const isUnclassified = (asm.predicted_class === 'unclassified') || 
                           (asm.top_prediction?.is_unclassified) || 
                           (asm.is_reliable === false) || 
                           (asm.assessment_status === 'unable_to_assess');

    // 1. Header: condition name, ID, date, confidence
    const predNameDisplay = isUnclassified
      ? 'No Confident Prediction / Unable to Assess'
      : (step1.predicted_condition || asm.predicted_name || 'Unknown');
    this._setText('res-predicted-name', predNameDisplay);
    this._setText('res-assessment-id', asm.id || '—');
    this._setText('res-assessment-date', new Date().toLocaleDateString('en-US', { year:'numeric', month:'short', day:'numeric' }));

    const score = asm.model_score || 0;
    const pct   = (score * 100).toFixed(1);
    const confBadge = document.getElementById('res-confidence-badge');
    if (confBadge) {
      if (isUnclassified) {
        confBadge.style.background = 'var(--amber-600, #d97706)';
        confBadge.style.color = '#fff';
        confBadge.textContent = `Inconclusive (${pct}% score)`;
      } else {
        confBadge.style.background = 'var(--teal-600, #0f766e)';
        confBadge.style.color = '#fff';
        confBadge.textContent = `${pct}% Match`;
      }
    }

    const reliability = isUnclassified
      ? 'Assessment Status: Unable to Assess (Insufficient Model Confidence)'
      : (score >= 0.75 ? 'High Confidence' : score >= 0.5 ? 'Moderate Confidence' : 'Low Confidence — Consult a Dermatologist');
    this._setText('res-reliability-label', reliability);

    // Uncertainty display
    if (asm.uncertainty_percent !== undefined) {
      const uncEl = document.getElementById('res-uncertainty-badge');
      if (uncEl) uncEl.textContent = `±${asm.uncertainty_percent.toFixed(1)}% uncertainty`;
    }

    // 2. Uploaded photo — always use the local data:URL for instant, auth-free display
    const photoEl = document.getElementById('res-uploaded-img');
    if (photoEl) {
      photoEl.src = _scanDataUrl
        || document.getElementById('scan-preview-img')?.src
        || (asm.image_filename ? `/uploads/${asm.image_filename}` : '#');
    }

    // 3. Clinical summary
    this._setText('res-clinical-summary', asm.clinical_summary || 'Analysis complete. Review results below.');

    // 4. Top-3 predictions
    const listEl = document.getElementById('res-top3-list');
    if (listEl && asm.top_predictions) {
      const badgeColors = ['badge-teal','badge-blue','badge-neutral'];
      let headerNotice = '';
      if (isUnclassified) {
        headerNotice = `<div class="p-2 mb-2 rounded small fw-600 text-amber" style="background:var(--amber-50, #fffbeb);border:1px solid var(--amber-200, #fef3c7);">
          <i class="fa-solid fa-triangle-exclamation me-1"></i> Technical Audit / Raw Model Probabilities (Not a Confirmed Diagnosis - Below Threshold)
        </div>`;
      }
      listEl.innerHTML = headerNotice + asm.top_predictions.slice(0,3).map((p, i) => `
        <div class="d-flex justify-content-between align-items-center p-3 rounded-lg mb-2" style="background:var(--bg-subtle);border:1px solid var(--border);">
          <div>
            <span class="fw-700 me-2" style="color:var(--teal-600);">#${i+1}</span>
            <span class="fw-600">${p.name || p.predicted_name || '—'}</span>
            <span class="text-muted small ms-2">(${p.category || p.predicted_class || ''})</span>
          </div>
          <span class="badge-pill ${isUnclassified ? 'badge-neutral' : (badgeColors[i] || 'badge-neutral')}">${((p.score||p.probability||0)*100).toFixed(1)}%</span>
        </div>`).join('');
    }

    // 5. Condition description
    const kb = asm.home_care_and_prevention || asm.knowledge_base || {};
    const topPred = asm.top_predictions?.[0] || {};
    if (isUnclassified) {
      this._setText('res-condition-description', 
        'No specific skin condition was diagnosed. The AI model evaluated your upload across all 9 supported skin disease classes, but the highest visual match score was below the required 40.0% confidence threshold (and/or model uncertainty was elevated). This frequently occurs when uploading photos of healthy normal skin, non-lesion areas, or conditions outside the model\'s 9 trained classes.');
    } else {
      this._setText('res-condition-description', kb.description || topPred.description ||
        `A dermatological condition showing visual features consistent with ${asm.predicted_name}.`);
    }

    // 6. XAI heatmap
    const origImg = document.getElementById('xai-img-original');
    const heatImg = document.getElementById('xai-img-heatmap');
    if (origImg) origImg.src = _scanDataUrl
      || document.getElementById('scan-preview-img')?.src
      || (asm.image_filename ? `/uploads/${asm.image_filename}` : '#');
    if (heatImg) {
      const src = asm.overlay_filename  ? `/uploads/${asm.overlay_filename}`
                : asm.heatmap_filename  ? `/uploads/${asm.heatmap_filename}`
                : asm.visual_explanation?.overlay_url || origImg?.src || '#';
      heatImg.src = src;
    }

    const xaiDesc = document.getElementById('xai-description');
    if (xaiDesc && asm.visual_explanation?.summary_text) {
      xaiDesc.textContent = asm.visual_explanation.summary_text;
    }

    // 6b. Patient-Friendly XAI breakdown rendering
    const pfXai = asm.patient_friendly_xai;
    if (pfXai) {
      this._setText('xai-pf-headline', pfXai.headline || `AI evaluated your upload against dataset features matching ${asm.predicted_name}.`);

      const visList = document.getElementById('xai-pf-visual-list');
      if (visList && pfXai.visual_factors) {
        visList.innerHTML = pfXai.visual_factors.map(f => `<li class="mb-1">${f}</li>`).join('');
      }

      const symList = document.getElementById('xai-pf-symptom-list');
      if (symList && pfXai.symptom_factors) {
        const items = [...(pfXai.symptom_factors || [])];
        if (pfXai.certainty_explanation) items.push(pfXai.certainty_explanation);
        symList.innerHTML = items.map(f => `<li class="mb-1">${f}</li>`).join('');
      }

      this._setText('xai-pf-alternatives', pfXai.alternative_reasoning || 'No strong competing alternative conditions.');
      this._setText('xai-pf-takeaway', pfXai.patient_takeaway || 'Consult a certified dermatologist for clinical diagnosis.');
    }

    // 7. Symptom bars & Severity
    const symBars = document.getElementById('res-symptom-bars');
    if (symBars) {
      const syms = {
        Itching:  asm.itching || 0,
        Pain:     asm.pain || 0,
        Redness:  asm.redness || 0,
        Duration: Math.min((asm.duration_days || 0) / 3.65, 10)
      };
      symBars.innerHTML = Object.entries(syms).map(([label, val]) => {
        const pct = Math.round(val * 10);
        const color = pct >= 70 ? 'var(--rose-500)' : pct >= 40 ? 'var(--amber-500)' : 'var(--teal-500)';
        return `<div class="col-md-6">
          <div class="d-flex justify-content-between mb-1">
            <span class="small fw-600">${label}</span>
            <span class="small text-muted">${val.toFixed ? val.toFixed(0) : val}/10</span>
          </div>
          <div style="background:var(--bg-muted);border-radius:999px;height:8px;">
            <div style="width:${pct}%;height:8px;border-radius:999px;background:${color};transition:width .5s;"></div>
          </div>
        </div>`;
      }).join('');
    }

    const sevScore = asm.severity_score || step3.severity_score || 0;
    const sevCat   = asm.severity_category || step3.severity_category || 'Mild';
    this._setText('res-severity-score', Math.round(sevScore));
    const sevBadge = document.getElementById('res-severity-badge');
    if (sevBadge) {
      const sevMap = { Mild:'badge-emerald', Moderate:'badge-amber', High:'badge-rose', Urgent:'badge-rose' };
      sevBadge.className = `badge-pill ${sevMap[sevCat] || 'badge-teal'}`;
      sevBadge.textContent = `${sevCat} Severity`;
    }

    // 8. Render Home Care & Prevention guidance sections (Reqs 19, 23, 24, 25, 26, 27, 31, 33)
    this.renderCareGuidance(kb);

    // 9. Escalation alert
    if (asm.is_escalated) {
      const escEl = document.getElementById('res-escalation-alert');
      const escReason = document.getElementById('res-escalation-reason');
      if (escEl) escEl.classList.remove('d-none');
      if (escReason && asm.escalation_reason) escReason.textContent = asm.escalation_reason;
    }

    _lastAsmId = asm.id;
  },

  // ── Render Care Guidance ──
  renderCareGuidance: function (kb) {
    if (!kb) return;

    const isFallback = kb.status === 'fallback';
    const guidanceType = isFallback ? 'General guidance'
      : kb.guidance_source === 'gemini' ? 'AI-assisted wording' : 'Supportive Home Care';
    this._setText('res-care-guidance-type', guidanceType);
    const generalNotice = document.getElementById('res-general-guidance-notice');
    if (generalNotice) generalNotice.hidden = !isFallback;

    if (kb.doctor_consultation_mandatory) {
      this._setText('res-doctor-mandatory-notice', kb.doctor_consultation_mandatory);
    }

    for (const [id, items] of [
      ['res-care-list', kb.supportive_care],
      ['res-preventive-list', kb.preventive_measures],
    ]) {
      const list = document.getElementById(id);
      if (!list) continue;
      list.replaceChildren(...(items || []).map(item => {
        const bullet = document.createElement('li');
        bullet.className = 'mb-2';
        bullet.textContent = item;
        return bullet;
      }));
    }

    if (kb.medical_treatment_info) {
      this._setText('res-medical-treatment-info', kb.medical_treatment_info);
    }

    // Things to Avoid (Req 25)
    const avoidList = document.getElementById('res-avoid-list');
    if (avoidList) {
      const items = kb.things_to_avoid || [];
      avoidList.innerHTML = items.map(item => `<li class="mb-2">${item}</li>`).join('');
    }

    // When to See a Dermatologist (Req 26)
    const docList = document.getElementById('res-dermatologist-list');
    if (docList) {
      const items = kb.when_to_see_doctor || [];
      docList.innerHTML = items.map(item => `<li class="mb-2">${item}</li>`).join('');
    }

    // Urgent Warning Signs (Req 27)
    const warnList = document.getElementById('res-warning-signs-list');
    if (warnList) {
      const items = kb.urgent_warning_signs || [];
      warnList.innerHTML = items.map(item => `<li class="mb-2 fw-600">${item}</li>`).join('');
    }

    // References & Metadata (Req 31)
    const refContainer = document.getElementById('res-references-container');
    if (refContainer) {
      const refs = kb.references || [];
      if (refs.length > 0) {
        refContainer.innerHTML = refs.map(r => `
          <div class="d-flex align-items-center justify-content-between p-2 rounded bg-teal-soft border-teal small">
            <div>
              <strong>${r.source || 'Medical Reference'}:</strong> ${r.title || 'Clinical Care Guide'}
            </div>
            ${r.url ? `<a href="${r.url}" target="_blank" rel="noopener" class="btn btn-ghost btn-sm py-0"><i class="fa-solid fa-arrow-up-right-from-square me-1"></i>View Source</a>` : ''}
          </div>`).join('');
      } else {
        refContainer.innerHTML = `<p class="text-muted small mb-0">Reviewed from recognized dermatological health organizations (AAD, NCI, Mayo Clinic).</p>`;
      }
    }

    this._setText('res-kb-version', kb.version || '1.0');
    this._setText('res-kb-reviewed', kb.last_reviewed || '2026-10-01');

    // Safety disclaimer (Req 33)
    if (kb.disclaimer) {
      this._setText('res-safety-disclaimer', kb.disclaimer);
    }
  },

  // ── Multilingual Selector (Req 32) ──
  _careGuidancePayload: function (lang) {
    const isUnclassified = (_currentAsm.predicted_class === 'unclassified') || 
                           (_currentAsm.top_prediction?.is_unclassified) || 
                           (_currentAsm.is_reliable === false) || 
                           (_currentAsm.assessment_status === 'unable_to_assess');
    const condition_code = isUnclassified ? 'unclassified' : (_currentAsm.predicted_class || 'unknown');

    return {
      condition_code:       condition_code,
      is_reliable:          _currentAsm.is_reliable !== false,
      assessment_status:    _currentAsm.assessment_status || (isUnclassified ? 'unable_to_assess' : 'success'),
      itching:              _currentAsm.itching || 0,
      pain:                 _currentAsm.pain || 0,
      duration_days:        _currentAsm.duration_days || 1,
      body_region:          _currentAsm.body_region || '',
      is_spreading:         document.getElementById('quest-spreading')?.checked || false,
      has_discharge:        document.getElementById('quest-discharge')?.checked || false,
      is_cracked_bleeding:  document.getElementById('quest-cracked')?.checked || false,
      new_cosmetic_product: document.getElementById('quest-cosmetic')?.checked || false,
      lang
    };
  },

  _bindLanguageSelector: function () {
    const fetchGuidanceForLang = async (lang) => {
      _currentLang = lang;
      if (!_currentAsm) return;
      const isUnclassified = (_currentAsm.predicted_class === 'unclassified') || 
                             (_currentAsm.top_prediction?.is_unclassified) || 
                             (_currentAsm.is_reliable === false) || 
                             (_currentAsm.assessment_status === 'unable_to_assess');

      try {
        const res = await fetch('/api/conditions/personalized-guidance', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this._careGuidancePayload(lang))
        });
        const data = await res.json();
        if (_currentLang !== lang) return;
        if (data.status === 'success' && data.guidance) {
          this.renderCareGuidance(data.guidance);
          if (!isUnclassified && data.guidance.status !== 'fallback' && data.guidance.condition_name) {
            this._setText('res-predicted-name', data.guidance.condition_name);
          }
          if (!isUnclassified && data.guidance.description) {
            this._setText('res-condition-description', data.guidance.description);
          }
        }
      } catch (err) {
        console.error('[ScannerModule] Language fetch error:', err);
      }

      // Re-fetch patient-friendly XAI explanation in new language
      try {
        const xaiRes = await fetch('/api/xai/explanation', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            predicted_class: _currentAsm.predicted_class,
            predicted_name: _currentAsm.predicted_name,
            model_score: _currentAsm.model_score,
            top_predictions: _currentAsm.top_predictions,
            itching: _currentAsm.itching,
            pain: _currentAsm.pain,
            redness: _currentAsm.redness,
            duration_days: _currentAsm.duration_days,
            model_uncertainty: _currentAsm.model_uncertainty,
            is_reliable: _currentAsm.is_reliable,
            assessment_status: _currentAsm.assessment_status,
            lang: _currentLang
          })
        });
        const xaiData = await xaiRes.json();
        if (xaiData.status === 'success' && xaiData.explanation) {
          const pfXai = xaiData.explanation;
          this._setText('xai-pf-headline', pfXai.headline);
          const visList = document.getElementById('xai-pf-visual-list');
          if (visList && pfXai.visual_factors) {
            visList.innerHTML = pfXai.visual_factors.map(f => `<li class="mb-1">${f}</li>`).join('');
          }
          const symList = document.getElementById('xai-pf-symptom-list');
          if (symList && pfXai.symptom_factors) {
            const items = [...(pfXai.symptom_factors || [])];
            if (pfXai.certainty_explanation) items.push(pfXai.certainty_explanation);
            symList.innerHTML = items.map(f => `<li class="mb-1">${f}</li>`).join('');
          }
          this._setText('xai-pf-alternatives', pfXai.alternative_reasoning);
          this._setText('xai-pf-takeaway', pfXai.patient_takeaway);
        }
      } catch (err) {
        console.error('[ScannerModule] XAI language fetch error:', err);
      }
    };

    window.addEventListener('languageChanged', (e) => {
      const newLang = e.detail ? e.detail.lang : 'en';
      fetchGuidanceForLang(newLang);
    });

    const btnGroup = document.getElementById('res-lang-btn-group');
    if (!btnGroup) return;

    btnGroup.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', async () => {
        const lang = btn.getAttribute('data-lang');
        if (lang === _currentLang) return;

        btnGroup.querySelectorAll('button').forEach(b => {
          b.classList.remove('btn-primary', 'active');
          b.classList.add('btn-outline-primary');
        });
        btn.classList.remove('btn-outline-primary');
        btn.classList.add('btn-primary', 'active');

        if (window.I18nModule) {
          window.I18nModule.setLanguage(lang);
        } else {
          fetchGuidanceForLang(lang);
        }
      });
    });
  },

  // ── Interactive Symptom Questionnaire (Req 28) ──
  _bindQuestionnaire: function () {
    const updateBtn = document.getElementById('quest-update-btn');
    if (!updateBtn) return;

    updateBtn.addEventListener('click', async () => {
      if (!_currentAsm) {
        Toast.warning('Please run an assessment first.');
        return;
      }

      updateBtn.disabled = true;
      updateBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>Updating Guidance…';

      const payload = this._careGuidancePayload(_currentLang);

      try {
        const res = await fetch('/api/conditions/personalized-guidance', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.status === 'success' && data.guidance) {
          this.renderCareGuidance(data.guidance);
          Toast.success('Personalized supportive care guidance updated!', 'Care Guidance Refined');
        } else {
          Toast.error('Failed to update guidance.', 'Error');
        }
      } catch (err) {
        Toast.error('Network error: ' + err.message, 'Error');
      } finally {
        updateBtn.disabled = false;
        updateBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate me-1"></i>Update Personalized Home Care';
      }
    });
  },

  // ── Result Action Buttons ──
  _bindResultButtons: function () {
    const pdfBtn = document.getElementById('res-download-pdf-btn');
    if (pdfBtn) {
      pdfBtn.addEventListener('click', () => {
        if (!_lastAsmId) { Toast.warning('No assessment to download.'); return; }
        pdfBtn.disabled = true;
        pdfBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Generating PDF…';
        const link = document.createElement('a');
        link.href = `/api/report/${_lastAsmId}`;
        link.download = `SkinSense_Report_${_lastAsmId}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(() => {
          pdfBtn.disabled = false;
          pdfBtn.innerHTML = '<i class="fa-solid fa-file-pdf me-2"></i>Download PDF Report';
        }, 2000);
      });
    }

    const trackBtn = document.getElementById('res-add-track-btn');
    if (trackBtn) {
      trackBtn.addEventListener('click', () => {
        if (!_lastAsmId) { Toast.warning('Please run an assessment first.'); return; }
        TrackingModule?.openAddToTrackModal?.(_lastAsmId);
      });
    }

    document.getElementById('res-view-track-btn')?.addEventListener('click', () => {
      if (this._linkedTrackId) TrackingModule.openTimeline(this._linkedTrackId);
    });

    const newScanBtn = document.getElementById('res-new-scan-btn');
    if (newScanBtn) {
      newScanBtn.addEventListener('click', () => this.reset());
    }
  },

  // ── XAI Opacity Slider ──
  _bindXaiSlider: function () {
    const slider   = document.getElementById('xai-opacity-slider');
    const valLabel = document.getElementById('xai-opacity-val');
    const heatImg  = document.getElementById('xai-img-heatmap');
    if (!slider) return;
    slider.addEventListener('input', () => {
      const opacity = parseInt(slider.value) / 100;
      if (heatImg) heatImg.style.opacity = opacity;
      if (valLabel) valLabel.textContent = `${slider.value}%`;
    });
  },

  // ── Reset wizard ──
  reset: function () {
    this.setTrack(null);
    this._linkedTrackId = null;
    document.getElementById('res-view-track-btn')?.classList.add('d-none');
    document.getElementById('scan-screening-consent').checked = false;
    _scanFile    = null;
    _scanDataUrl = null;
    _lastAsmId   = null;
    _currentAsm  = null;
    const fi = document.getElementById('scan-file-input');
    if (fi) fi.value = '';

    document.getElementById('scan-preview-container')?.classList.add('d-none');
    document.getElementById('scan-dropzone')?.classList.remove('d-none');
    document.getElementById('scanner-step-1')?.classList.remove('d-none');
    document.getElementById('scanner-step-2')?.classList.add('d-none');
    document.getElementById('scanner-step-loading')?.classList.add('d-none');
    document.getElementById('scan-results-section')?.classList.add('d-none');
    document.getElementById('res-escalation-alert')?.classList.add('d-none');

    const nextBtn = document.getElementById('step1-next-btn');
    if (nextBtn) nextBtn.disabled = true;

    ['itching','pain','redness'].forEach(id => {
      const inp = document.getElementById('input-' + id);
      const lbl = document.getElementById('val-' + id);
      if (inp) inp.value = 0;
      if (lbl) lbl.textContent = '0 / 10';
    });

    for (let i = 1; i <= 3; i++) {
      const circle = document.getElementById(`step-circle-${i}`);
      const label  = document.getElementById(`step-label-${i}`);
      if (circle) { circle.className = 'step-circle' + (i===1?' active':''); circle.innerHTML = i; }
      if (label)  label.className = 'step-label' + (i===1?' active':'');
    }
    ['step-line-12','step-line-23'].forEach(id => document.getElementById(id)?.classList.remove('active'));

    window.scrollTo({ top: 0, behavior: 'smooth' });
  },

  _setText: function (id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }
};

