-- SkinSense Enhanced Database Schema v2.0
-- Adds: audit_log, lesion_tracking, dermatologist_queue, login_attempts,
--       notifications, user_profile_ext tables

CREATE TABLE IF NOT EXISTS users (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name          TEXT NOT NULL,
    email              TEXT UNIQUE NOT NULL,
    password_hash      TEXT NOT NULL,
    role               TEXT NOT NULL DEFAULT 'patient' CHECK(role IN ('patient', 'admin', 'dermatologist')),
    is_active          INTEGER DEFAULT 1,
    email_verified     INTEGER DEFAULT 0,
    verification_token TEXT,
    reset_token        TEXT,
    reset_token_expires TIMESTAMP,
    fitzpatrick_type   INTEGER CHECK(fitzpatrick_type BETWEEN 1 AND 6),
    date_of_birth      DATE,
    phone_number       TEXT,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login         TIMESTAMP
);

CREATE TABLE IF NOT EXISTS assessments (
    id                        TEXT PRIMARY KEY,
    user_id                   INTEGER,
    image_filename            TEXT,
    image_hash                TEXT,
    predicted_class           TEXT,
    predicted_name            TEXT,
    model_score               REAL,
    model_id                  TEXT,
    model_uncertainty         REAL,
    uncertainty_std           REAL,
    top_predictions_json      TEXT,
    quality_status            TEXT,
    patient_name              TEXT,
    patient_age               INTEGER,
    body_region               TEXT,
    itching                   INTEGER,
    pain                      INTEGER,
    redness                   INTEGER,
    duration_days             INTEGER,
    fever_level               INTEGER,
    burning_level             INTEGER,
    severity_score            REAL,
    severity_category         TEXT,
    contributing_factors_json TEXT,
    clinical_summary          TEXT,
    heatmap_filename          TEXT,
    overlay_filename          TEXT,
    explanation_method        TEXT,
    fuzzy_explanation_json    TEXT,
    shap_explanation_json     TEXT,
    review_status             TEXT DEFAULT 'pending' CHECK(review_status IN ('pending','reviewed','escalated','closed')),
    dermatologist_id          INTEGER,
    dermatologist_notes       TEXT,
    dermatologist_diagnosis   TEXT,
    is_escalated              INTEGER DEFAULT 0,
    escalation_reason         TEXT,
    pdf_filename              TEXT,
    created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(dermatologist_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER,
    conversation_id TEXT NOT NULL,
    assessment_id   TEXT,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    image_attached  TEXT,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(assessment_id) REFERENCES assessments(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS model_metadata (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name   TEXT NOT NULL,
    architecture TEXT NOT NULL,
    version      TEXT NOT NULL,
    num_classes  INTEGER NOT NULL,
    accuracy     REAL NOT NULL,
    metrics_json TEXT NOT NULL,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- HIPAA Audit Log (append-only)
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id     TEXT,
    user_email  TEXT,
    action      TEXT NOT NULL,
    resource    TEXT,
    ip_address  TEXT,
    user_agent  TEXT,
    status      TEXT DEFAULT 'success',
    details     TEXT
);

-- Longitudinal Lesion Tracking
CREATE TABLE IF NOT EXISTS lesion_tracks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    track_name      TEXT NOT NULL,
    body_region     TEXT,
    first_seen      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active       INTEGER DEFAULT 1,
    notes           TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lesion_track_assessments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id        INTEGER NOT NULL,
    assessment_id   TEXT NOT NULL,
    order_index     INTEGER DEFAULT 0,
    change_notes    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(track_id) REFERENCES lesion_tracks(id) ON DELETE CASCADE,
    FOREIGN KEY(assessment_id) REFERENCES assessments(id) ON DELETE CASCADE
);

-- Dermatologist Review Queue
CREATE TABLE IF NOT EXISTS review_queue (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id         TEXT NOT NULL,
    patient_id            INTEGER NOT NULL,
    assigned_derm_id      INTEGER,
    priority              TEXT DEFAULT 'normal' CHECK(priority IN ('urgent','high','normal','low')),
    queue_reason          TEXT,
    status                TEXT DEFAULT 'pending' CHECK(status IN ('pending','in_review','completed','rejected')),
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_at           TIMESTAMP,
    completed_at          TIMESTAMP,
    derm_verdict          TEXT,
    derm_notes            TEXT,
    FOREIGN KEY(assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
    FOREIGN KEY(patient_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(assigned_derm_id) REFERENCES users(id) ON DELETE SET NULL
);

-- In-DB Login Rate Limiting (complementary to in-memory)
CREATE TABLE IF NOT EXISTS login_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    identifier  TEXT NOT NULL,
    attempt_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success     INTEGER DEFAULT 0,
    ip_address  TEXT
);

-- Medical Knowledge Base (Home Care, Prevention, Avoid & Medical Guidance)
CREATE TABLE IF NOT EXISTS medical_knowledge_base (
    condition_code           TEXT PRIMARY KEY,
    condition_name           TEXT NOT NULL,
    category                 TEXT NOT NULL,
    risk_level               TEXT NOT NULL,
    prevalence               TEXT,
    description              TEXT NOT NULL,
    common_symptoms_json     TEXT NOT NULL,
    supportive_care_json     TEXT NOT NULL,
    preventive_measures_json TEXT NOT NULL,
    things_to_avoid_json     TEXT NOT NULL,
    when_to_see_doctor_json  TEXT NOT NULL,
    urgent_warning_signs_json TEXT NOT NULL,
    medical_treatment_info   TEXT NOT NULL,
    references_json          TEXT NOT NULL,
    translations_json        TEXT,
    version                  TEXT DEFAULT '1.0',
    last_reviewed            TEXT DEFAULT '2026-10-01',
    status                   TEXT DEFAULT 'approved' CHECK(status IN ('approved','draft','archived')),
    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_login_attempts_id  ON login_attempts(identifier);
CREATE INDEX IF NOT EXISTS idx_audit_user         ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action       ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_assessments_user   ON assessments(user_id);
CREATE INDEX IF NOT EXISTS idx_assessments_class  ON assessments(predicted_class);
CREATE INDEX IF NOT EXISTS idx_lesion_track_user  ON lesion_tracks(user_id);
CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_kb_status          ON medical_knowledge_base(status);
