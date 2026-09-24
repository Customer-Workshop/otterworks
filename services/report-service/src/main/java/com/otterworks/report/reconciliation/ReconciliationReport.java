package com.otterworks.report.reconciliation;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

import java.util.ArrayList;
import java.util.List;

/** JSON shape of one reconciliation run (CONTRACTS §10.2). */
@JsonPropertyOrder({"run_id", "namespace", "generated_at", "status", "started_at", "finished_at",
    "tables", "failures", "class_totals", "sessions", "closes"})
public class ReconciliationReport {

    @JsonProperty("run_id")
    public String runId;
    @JsonProperty("namespace")
    public String namespace;
    @JsonProperty("generated_at")
    public String generatedAt;
    @JsonProperty("status")
    public String status;
    @JsonProperty("started_at")
    public String startedAt;
    @JsonProperty("finished_at")
    public String finishedAt;
    @JsonProperty("tables")
    public List<TableRow> tables = new ArrayList<TableRow>();
    @JsonProperty("failures")
    public List<FailureRow> failures = new ArrayList<FailureRow>();
    @JsonProperty("class_totals")
    public List<ClassTotalRow> classTotals = new ArrayList<ClassTotalRow>();
    @JsonProperty("sessions")
    public List<SessionLink> sessions = new ArrayList<SessionLink>();
    @JsonProperty("closes")
    public boolean closes;

    /** One row of {@code mig.v_reconciliation_tables}. */
    @JsonPropertyOrder({"table", "extracted", "loaded", "validated", "purged", "failed", "rejected",
        "validate_failed", "purge_intended", "purge_dry_run", "closes"})
    public static class TableRow {
        @JsonProperty("table")
        public String table;
        @JsonProperty("extracted")
        public long extracted;
        @JsonProperty("loaded")
        public long loaded;
        @JsonProperty("validated")
        public long validated;
        @JsonProperty("purged")
        public long purged;
        @JsonProperty("failed")
        public long failed;
        @JsonProperty("rejected")
        public long rejected;
        @JsonProperty("validate_failed")
        public long validateFailed;
        @JsonProperty("purge_intended")
        public long purgeIntended;
        @JsonProperty("purge_dry_run")
        @JsonInclude(JsonInclude.Include.NON_NULL)
        public Boolean purgeDryRun;
        @JsonProperty("closes")
        public boolean closes;
    }

    /** One row of {@code mig.v_reconciliation_failures}. */
    @JsonPropertyOrder({"table", "source_key", "rule", "stage", "field", "sqlstate", "native_error", "error",
        "issue"})
    public static class FailureRow {
        @JsonProperty("table")
        public String table;
        @JsonProperty("source_key")
        public String sourceKey;
        @JsonProperty("rule")
        public String rule;
        @JsonProperty("stage")
        public String stage;
        @JsonProperty("field")
        public String field;
        @JsonProperty("sqlstate")
        public String sqlstate;
        @JsonProperty("native_error")
        public Integer nativeError;
        @JsonProperty("error")
        public String error;
        @JsonProperty("issue")
        public String issue;
    }

    /** One row of {@code mig.class_totals} - the MIG-07 evidence. */
    @JsonPropertyOrder({"table", "class", "source_count", "target_count", "source_sum", "target_sum", "matches"})
    public static class ClassTotalRow {
        @JsonProperty("table")
        public String table;
        @JsonProperty("class")
        public String retentionClass;
        @JsonProperty("source_count")
        public long sourceCount;
        @JsonProperty("target_count")
        public long targetCount;
        @JsonProperty("source_sum")
        public String sourceSum;
        @JsonProperty("target_sum")
        public String targetSum;
        @JsonProperty("matches")
        public boolean matches;
    }

    /** One row of {@code mig.run_sessions}. */
    @JsonPropertyOrder({"label", "url"})
    public static class SessionLink {
        @JsonProperty("label")
        public String label;
        @JsonProperty("url")
        public String url;

        public SessionLink() {
        }

        public SessionLink(String label, String url) {
            this.label = label;
            this.url = url;
        }
    }

    /** One entry of the run listing ({@code GET /api/reports/reconciliation}). */
    @JsonPropertyOrder({"run_id", "status", "started_at", "finished_at", "closes"})
    public static class RunSummary {
        @JsonProperty("run_id")
        public String runId;
        @JsonProperty("status")
        public String status;
        @JsonProperty("started_at")
        public String startedAt;
        @JsonProperty("finished_at")
        public String finishedAt;
        @JsonProperty("closes")
        public boolean closes;
    }
}
