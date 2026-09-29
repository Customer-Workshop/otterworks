package com.boxoffice.common;

/** Every module writes here inside its own business transaction. */
public final class AuditLog {

    private AuditLog() {
    }

    public static void record(String module, String action, String entityRef, String detail) {
        Db.update("INSERT INTO audit_log (module, action, entity_ref, detail) VALUES (?, ?, ?, ?)",
                module, action, entityRef, detail);
    }
}
