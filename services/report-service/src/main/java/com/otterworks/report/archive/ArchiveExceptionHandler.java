package com.otterworks.report.archive;

import com.otterworks.report.reconciliation.ReconciliationController;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Maps the archive exceptions to the contracted status codes: feature off -> 404 with a hint,
 * misconfigured or unreachable store -> 503. Scoped to the archive controllers so the golden
 * report endpoints keep their existing error behaviour.
 */
@RestControllerAdvice(assignableTypes = {ArchiveController.class, ReconciliationController.class})
public class ArchiveExceptionHandler {

    private static final Logger logger = LoggerFactory.getLogger(ArchiveExceptionHandler.class);

    @ExceptionHandler(ArchiveFeatureDisabledException.class)
    public ResponseEntity<Map<String, String>> featureOff(ArchiveFeatureDisabledException e) {
        Map<String, String> body = new LinkedHashMap<String, String>();
        body.put("error", "archive feature is not enabled");
        body.put("hint", ArchiveFeatureDisabledException.HINT);
        return ResponseEntity.status(HttpStatus.NOT_FOUND).contentType(MediaType.APPLICATION_JSON).body(body);
    }

    @ExceptionHandler(ArchiveStoreUnavailableException.class)
    public ResponseEntity<Map<String, String>> unavailable(ArchiveStoreUnavailableException e) {
        logger.error("archive store unavailable: {}", e.getMessage(), e.getCause());
        Map<String, String> body = new LinkedHashMap<String, String>();
        body.put("error", "archive store unavailable");
        body.put("detail", e.getMessage());
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }
}
