package com.otterworks.report.reconciliation;

import com.otterworks.report.archive.ArchiveFeatureDisabledException;
import com.otterworks.report.archive.ArchiveStoreType;
import com.otterworks.report.reconciliation.ReconciliationReport.RunSummary;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Reconciliation report endpoints (CONTRACTS §10.1), served under both {@code /api/reports} and
 * {@code /api/v1/reports}. Only meaningful when {@code ARCHIVE_STORE=postgresql} (or azuresql); on the BEFORE
 * deployment they answer 404 {@code {"error":"no migration in this namespace"}}.
 */
@RestController
@RequestMapping({"/api/reports/reconciliation", "/api/v1/reports/reconciliation"})
public class ReconciliationController {

    static final String LATEST = "latest";
    static final MediaType TEXT_CSV_UTF8 = new MediaType("text", "csv", StandardCharsets.UTF_8);
    private static final DateTimeFormatter ISO_UTC = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'");

    private final ReconciliationRepository repository;

    public ReconciliationController(ReconciliationRepository repository) {
        this.repository = repository;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Object> list() {
        ResponseEntity<Object> gate = gate();
        if (gate != null) {
            return gate;
        }
        return ResponseEntity.ok((Object) repository.listRuns());
    }

    @GetMapping("/{runId:.+}")
    public ResponseEntity<Object> run(@PathVariable("runId") String runId) {
        if (runId.endsWith(".csv")) {
            return csv(runId.substring(0, runId.length() - 4));
        }
        if (runId.endsWith(".html")) {
            return html(runId.substring(0, runId.length() - 5));
        }
        ResponseEntity<Object> gate = gate();
        if (gate != null) {
            return gate;
        }
        Optional<ReconciliationReport> report = load(runId);
        if (!report.isPresent()) {
            return runNotFound();
        }
        return ResponseEntity.ok((Object) report.get());
    }

    private ResponseEntity<Object> csv(String runId) {
        ResponseEntity<Object> gate = gate();
        if (gate != null) {
            return gate;
        }
        Optional<ReconciliationReport> report = load(runId);
        if (!report.isPresent()) {
            return runNotFound();
        }
        String body = ReconciliationCsvWriter.write(report.get());
        return ResponseEntity.ok()
                .contentType(TEXT_CSV_UTF8)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"reconciliation-" + report.get().runId + ".csv\"")
                .body((Object) body.getBytes(StandardCharsets.UTF_8));
    }

    private ResponseEntity<Object> html(String runId) {
        ResponseEntity<Object> gate = gate();
        if (gate != null) {
            return gate;
        }
        Optional<ReconciliationReport> report = load(runId);
        if (!report.isPresent()) {
            return runNotFound();
        }
        return ResponseEntity.ok()
                .contentType(new MediaType("text", "html", StandardCharsets.UTF_8))
                .body((Object) ReconciliationHtmlRenderer.render(report.get()));
    }

    /** {@code latest} resolves to the newest run of the namespace. */
    private Optional<ReconciliationReport> load(String runId) {
        String resolved = runId;
        if (LATEST.equals(runId)) {
            List<RunSummary> runs = repository.listRuns();
            if (runs.isEmpty()) {
                return Optional.empty();
            }
            resolved = runs.get(0).runId;
        }
        Optional<ReconciliationReport> report = repository.findRun(resolved);
        if (report.isPresent()) {
            report.get().generatedAt = Instant.now().atOffset(ZoneOffset.UTC).format(ISO_UTC);
        }
        return report;
    }

    /**
     * Null when the ledger can be read. Feature off -> 404 with the enablement hint (golden
     * behaviour untouched); {@code db2} -> the contracted 404; any other value -> 503 via the
     * registry's unavailable exception.
     */
    private ResponseEntity<Object> gate() {
        if (repository.isAvailable()) {
            return null;
        }
        if (repository.storeType() == ArchiveStoreType.OFF) {
            Map<String, String> body = new LinkedHashMap<String, String>();
            body.put("error", "no migration in this namespace");
            body.put("hint", ArchiveFeatureDisabledException.HINT);
            return ResponseEntity.status(HttpStatus.NOT_FOUND).contentType(MediaType.APPLICATION_JSON)
                    .body((Object) body);
        }
        if (repository.storeType() == ArchiveStoreType.DB2) {
            Map<String, String> body = Collections.singletonMap("error", "no migration in this namespace");
            return ResponseEntity.status(HttpStatus.NOT_FOUND).contentType(MediaType.APPLICATION_JSON)
                    .body((Object) body);
        }
        repository.listRuns();
        return null;
    }

    private static ResponseEntity<Object> runNotFound() {
        Map<String, String> body = Collections.singletonMap("error", "run not found");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).contentType(MediaType.APPLICATION_JSON).body((Object) body);
    }
}
