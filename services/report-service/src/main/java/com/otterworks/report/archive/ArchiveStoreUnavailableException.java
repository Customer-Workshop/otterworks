package com.otterworks.report.archive;

/** The selected archive store is misconfigured or cannot be reached (answered as HTTP 503). */
public class ArchiveStoreUnavailableException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public ArchiveStoreUnavailableException(String message) {
        super(message);
    }

    public ArchiveStoreUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
