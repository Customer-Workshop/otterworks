package com.otterworks.report.archive;

/** {@code ARCHIVE_STORE} is not set: the archive feature is off (answered as HTTP 404 with a hint). */
public class ArchiveFeatureDisabledException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public static final String HINT =
            "archive feature is off; set ARCHIVE_STORE=db2 or ARCHIVE_STORE=azuresql to enable it";

    public ArchiveFeatureDisabledException() {
        super(HINT);
    }
}
