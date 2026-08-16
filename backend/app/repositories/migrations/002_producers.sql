CREATE TABLE producers (
    id TEXT PRIMARY KEY,
    center_id TEXT NOT NULL REFERENCES centers(id) ON DELETE RESTRICT,
    display_name TEXT NOT NULL,
    municipality TEXT NOT NULL,
    data_origin TEXT NOT NULL CHECK(data_origin IN ('demonstration', 'pilot', 'operational')),
    consent_status TEXT NOT NULL CHECK(consent_status IN ('demonstration', 'granted', 'withdrawn')),
    consent_updated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

ALTER TABLE plots ADD COLUMN producer_id TEXT REFERENCES producers(id) ON DELETE RESTRICT;

CREATE INDEX idx_producers_center ON producers(center_id);
CREATE INDEX idx_plots_producer ON plots(producer_id);
