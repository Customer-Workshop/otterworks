package com.otterworks.report.archive;

import java.util.Optional;

/**
 * Read-only access to the archived retention history (DOCARCH / FILEAUD / RETNPLCY),
 * implemented once per backing store. Both implementations return the same DTO with
 * byte-identical text so the presenter can diff BEFORE and AFTER.
 */
public interface ArchiveStore {

    /** Wire name of the store ({@code db2}, {@code postgresql} or {@code azuresql}). */
    String storeName();

    /** All versions (with events and policy) of one document, or empty when none is archived. */
    Optional<ArchiveDocument> findDocument(String docId);

    /** Cheap connectivity check used by {@code /health/archive}; throws on failure. */
    void ping();
}
