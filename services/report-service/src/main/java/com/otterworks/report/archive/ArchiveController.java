package com.otterworks.report.archive;

import com.otterworks.report.archive.ArchiveDocument.ArchiveEvent;
import com.otterworks.report.archive.ArchiveDocument.ArchiveVersion;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Retention history of one archived document from the selected {@code ARCHIVE_STORE}
 * (CONTRACTS §10.4) plus its business hashes (§7).
 */
@RestController
@RequestMapping({"/api/archive/documents", "/api/v1/archive/documents", "/api/v1/reports/archive/documents"})
public class ArchiveController {

    private final ArchiveStoreRegistry registry;

    public ArchiveController(ArchiveStoreRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/{docId}")
    public ResponseEntity<Object> document(@PathVariable("docId") String docId,
                                           @RequestParam(value = "raw", defaultValue = "false") boolean raw) {
        Optional<ArchiveDocument> found = registry.store().findDocument(docId);
        if (!found.isPresent()) {
            return notFound(docId);
        }
        ArchiveDocument document = found.get();
        return ResponseEntity.ok((Object) (raw ? document : document.withoutRaw()));
    }

    /**
     * Business hash per DOCARCH version and per FILEAUD event, plus a document-level digest
     * over the ordered row hashes, so the presenter can compare before and after at a glance.
     */
    @GetMapping("/{docId}/hash")
    public ResponseEntity<Object> hash(@PathVariable("docId") String docId) {
        Optional<ArchiveDocument> found = registry.store().findDocument(docId);
        if (!found.isPresent()) {
            return notFound(docId);
        }
        ArchiveDocument document = found.get();
        List<Map<String, Object>> versions = new ArrayList<Map<String, Object>>();
        StringBuilder all = new StringBuilder();
        for (ArchiveVersion version : document.getVersions()) {
            String versionHash = BusinessHash.docarch(version);
            all.append(versionHash).append('\n');
            List<Map<String, Object>> events = new ArrayList<Map<String, Object>>();
            for (ArchiveEvent event : version.events) {
                String eventHash = BusinessHash.fileaud(event);
                all.append(eventHash).append('\n');
                Map<String, Object> e = new LinkedHashMap<String, Object>();
                e.put("audit_key", event.auditKey);
                e.put("row_hash", eventHash);
                events.add(e);
            }
            Map<String, Object> v = new LinkedHashMap<String, Object>();
            v.put("arch_key", version.archKey);
            v.put("version_no", version.versionNo);
            v.put("row_hash", versionHash);
            v.put("events", events);
            versions.add(v);
        }
        Map<String, Object> body = new LinkedHashMap<String, Object>();
        body.put("doc_id", document.getDocId());
        body.put("store", document.getStore());
        body.put("algorithm", "SHA-256 over '|'-joined manifest hash_columns (CONTRACTS §7)");
        body.put("document_hash", BusinessHash.sha256Hex(all.toString()));
        body.put("versions", versions);
        return ResponseEntity.ok((Object) body);
    }

    private static ResponseEntity<Object> notFound(String docId) {
        Map<String, String> body = new LinkedHashMap<String, String>();
        body.put("error", "document not found");
        body.put("doc_id", Db2Text.rtrim(docId));
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body((Object) Collections.unmodifiableMap(body));
    }
}
