package com.otterworks.report.controller;

import com.otterworks.report.archive.ArchiveStoreRegistry;
import com.otterworks.report.archive.ArchiveStoreType;
import com.otterworks.report.archive.ArchiveStoreUnavailableException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Health check endpoint.
 */
@RestController
public class HealthController {

    private final ArchiveStoreRegistry archive;

    public HealthController(ArchiveStoreRegistry archive) {
        this.archive = archive;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        // LEGACY: Returns raw Map instead of a typed response object
        Map<String, String> response = new HashMap<>();
        response.put("status", "healthy");
        response.put("service", "report-service");
        response.put("version", "0.1.0");
        return response;
    }

    /**
     * Pings the selected archive store. Independent of {@link #health()} so the liveness /
     * readiness probes never depend on Db2 or Azure SQL being reachable.
     */
    @GetMapping("/health/archive")
    public ResponseEntity<Map<String, Object>> archiveHealth() {
        Map<String, Object> response = new LinkedHashMap<String, Object>();
        response.put("store", archive.type().wireName());
        response.put("namespace", archive.namespace());
        if (archive.type() == ArchiveStoreType.OFF) {
            response.put("status", "disabled");
            return ResponseEntity.ok(response);
        }
        try {
            archive.store().ping();
            response.put("status", "healthy");
            return ResponseEntity.ok(response);
        } catch (ArchiveStoreUnavailableException e) {
            response.put("status", "unavailable");
            response.put("detail", e.getMessage());
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(response);
        }
    }
}
