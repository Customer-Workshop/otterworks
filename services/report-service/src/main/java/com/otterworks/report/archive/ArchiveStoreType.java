package com.otterworks.report.archive;

import java.util.Locale;

/**
 * Value of the {@code ARCHIVE_STORE} environment variable.
 *
 * {@link #OFF} is the golden-app default (feature disabled). {@link #INVALID} is any
 * unrecognised value: the service still starts but the archive endpoints answer 503.
 */
public enum ArchiveStoreType {
    OFF("off"),
    DB2("db2"),
    POSTGRESQL("postgresql"),
    AZURESQL("azuresql"),
    INVALID("invalid");

    private final String wireName;

    ArchiveStoreType(String wireName) {
        this.wireName = wireName;
    }

    public String wireName() {
        return wireName;
    }

    /** Stores that carry the {@code mig.*} migration ledger alongside {@code arch.*}. */
    public boolean hasMigrationLedger() {
        return this == POSTGRESQL || this == AZURESQL;
    }

    public static ArchiveStoreType parse(String raw) {
        if (raw == null || raw.trim().isEmpty()) {
            return OFF;
        }
        String value = raw.trim().toLowerCase(Locale.ROOT);
        if ("db2".equals(value)) {
            return DB2;
        }
        if ("postgresql".equals(value) || "postgres".equals(value)) {
            return POSTGRESQL;
        }
        if ("azuresql".equals(value)) {
            return AZURESQL;
        }
        if ("off".equals(value) || "none".equals(value)) {
            return OFF;
        }
        return INVALID;
    }
}
