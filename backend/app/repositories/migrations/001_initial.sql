CREATE TABLE centers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    municipality TEXT NOT NULL,
    version TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE crop_profiles (
    id TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
    version TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE plots (
    id TEXT PRIMARY KEY,
    center_id TEXT NOT NULL REFERENCES centers(id),
    crop_profile_id TEXT NOT NULL REFERENCES crop_profiles(id),
    name TEXT NOT NULL,
    municipality TEXT NOT NULL,
    boundary_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE readings (
    id TEXT PRIMARY KEY,
    plot_id TEXT NOT NULL REFERENCES plots(id) ON DELETE RESTRICT,
    latitude REAL NOT NULL CHECK(latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL CHECK(longitude BETWEEN -180 AND 180),
    n_pct REAL NOT NULL CHECK(n_pct BETWEEN 0 AND 100),
    p_pct REAL NOT NULL CHECK(p_pct BETWEEN 0 AND 100),
    k_pct REAL NOT NULL CHECK(k_pct BETWEEN 0 AND 100),
    basis TEXT NOT NULL CHECK(basis = 'elemental_mass_pct'),
    measured_at TEXT NOT NULL,
    client_id TEXT NOT NULL UNIQUE,
    valid_for_model INTEGER NOT NULL DEFAULT 1 CHECK(valid_for_model IN (0, 1)),
    suspicious INTEGER NOT NULL DEFAULT 0 CHECK(suspicious IN (0, 1)),
    anomaly_method TEXT,
    anomaly_score REAL,
    anomaly_reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE formulations (
    id TEXT PRIMARY KEY,
    center_id TEXT NOT NULL REFERENCES centers(id),
    label TEXT NOT NULL,
    formulation_json TEXT NOT NULL,
    available INTEGER NOT NULL CHECK(available IN (0, 1)),
    valid_from TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(center_id, label)
);

CREATE TABLE model_runs (
    id TEXT PRIMARY KEY,
    plot_id TEXT NOT NULL REFERENCES plots(id),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    observation_count INTEGER NOT NULL,
    metrics_json TEXT NOT NULL,
    inference_ms REAL NOT NULL,
    input_hash TEXT NOT NULL,
    limitations_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE packages (
    id TEXT PRIMARY KEY,
    plot_id TEXT NOT NULL REFERENCES plots(id),
    model_run_id TEXT NOT NULL REFERENCES model_runs(id),
    contract_version TEXT NOT NULL CHECK(contract_version = '2.0'),
    snapshot_json TEXT NOT NULL,
    degraded INTEGER NOT NULL CHECK(degraded IN (0, 1)),
    generated_at TEXT NOT NULL
);

CREATE TABLE proposals (
    id TEXT PRIMARY KEY,
    plot_id TEXT NOT NULL REFERENCES plots(id),
    package_id TEXT NOT NULL REFERENCES packages(id),
    proposal_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status = 'pending'),
    validation_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE decisions (
    id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES proposals(id),
    action TEXT NOT NULL CHECK(action IN ('accept', 'reject', 'modify', 'refer')),
    resulting_status TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK(actor_type IN ('farmer', 'technician', 'system')),
    actor_id TEXT NOT NULL,
    modification_json TEXT,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE audit_log (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE external_api_cache (
    source TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    payload_json TEXT,
    fetched_at TEXT,
    expires_at TEXT,
    source_url TEXT,
    last_failure_at TEXT,
    last_error TEXT,
    failure_count INTEGER NOT NULL DEFAULT 0,
    circuit_open_until TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(source, cache_key)
);

CREATE INDEX idx_plots_center ON plots(center_id);
CREATE INDEX idx_readings_plot_time ON readings(plot_id, measured_at);
CREATE INDEX idx_readings_plot_valid ON readings(plot_id, valid_for_model);
CREATE INDEX idx_formulations_center_active ON formulations(center_id, available);
CREATE INDEX idx_model_runs_plot_created ON model_runs(plot_id, created_at DESC);
CREATE INDEX idx_packages_plot_generated ON packages(plot_id, generated_at DESC);
CREATE INDEX idx_proposals_plot_created ON proposals(plot_id, created_at DESC);
CREATE INDEX idx_decisions_proposal_created ON decisions(proposal_id, created_at);
CREATE INDEX idx_audit_entity_sequence ON audit_log(entity_type, entity_id, sequence);

CREATE TRIGGER audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TRIGGER audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TRIGGER proposals_audit_insert
AFTER INSERT ON proposals
BEGIN
    INSERT INTO audit_log(event_id, event_type, entity_type, entity_id, actor, payload_json, created_at)
    VALUES ('trigger-proposal-' || NEW.id, 'proposal_created', 'proposal', NEW.id, 'system', '{}', NEW.created_at);
END;

CREATE TRIGGER decisions_audit_insert
AFTER INSERT ON decisions
BEGIN
    INSERT INTO audit_log(event_id, event_type, entity_type, entity_id, actor, payload_json, created_at)
    VALUES ('trigger-decision-' || NEW.id, 'decision_recorded', 'proposal', NEW.proposal_id,
            NEW.actor_type || ':' || NEW.actor_id, '{}', NEW.created_at);
END;
