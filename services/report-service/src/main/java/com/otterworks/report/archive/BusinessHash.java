package com.otterworks.report.archive;

import com.otterworks.report.archive.ArchiveDocument.ArchiveEvent;
import com.otterworks.report.archive.ArchiveDocument.ArchiveVersion;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.List;

/**
 * Business hash per CONTRACTS §7: {@code SHA-256(UTF-8(render(c1) || '|' || render(c2) ...))}
 * over the manifest's {@code hash_columns} in order, shown as uppercase hex.
 *
 * Key columns are hashed with their padding kept (so the Db2 row and its right-trimmed Azure
 * copy differ exactly when MIG-04 applies); every other CHAR is right-trimmed; DECIMALs carry
 * eight fraction digits; timestamps use the Db2 text form; the DATE renders as {@code YYYYMMDD}.
 */
public final class BusinessHash {

    static final List<String> DOCARCH_COLUMNS = Arrays.asList(
            "ARCH_KEY", "DOC_ID", "VERSION_NO", "RETENTION_CLASS", "LAST_ACCESS_TS", "STORAGE_CHARGE",
            "UNIT_RATE", "OWNER_NAME", "DISPOSITION_DT", "LEGAL_HOLD_FLAG", "CONTENT_SHA256", "BYTE_SIZE");

    static final List<String> FILEAUD_COLUMNS = Arrays.asList(
            "AUDIT_KEY", "ARCH_KEY", "EVENT_TYPE", "EVENT_TS", "ACTOR_ID", "RETENTION_CLASS",
            "DISPOSITION_CODE", "CLIENT_IP", "DETAIL_TEXT");

    private BusinessHash() {
    }

    /** DOCARCH row hash; the key {@code ARCH_KEY} is taken from {@code raw} (padding kept). */
    public static String docarch(ArchiveVersion v) {
        return sha256Hex(String.join("|",
                v.raw.archKey,
                Db2Text.rtrim(v.raw.docId),
                String.valueOf(v.versionNo),
                v.retentionClass,
                v.lastAccessTs,
                v.storageCharge,
                v.unitRate,
                v.ownerName,
                v.raw.dispositionDt,
                Db2Text.rtrim(v.raw.legalHoldFlag),
                v.contentSha256,
                String.valueOf(v.byteSize)));
    }

    /** FILEAUD row hash; the key {@code AUDIT_KEY} is taken from {@code raw} (padding kept). */
    public static String fileaud(ArchiveEvent e) {
        return sha256Hex(String.join("|",
                e.raw.auditKey,
                Db2Text.rtrim(e.raw.archKey),
                e.eventType,
                e.eventTs,
                e.actorId,
                e.retentionClass,
                e.dispositionCode,
                e.clientIp,
                e.detailText));
    }

    static String sha256Hex(String text) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(text.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder(bytes.length * 2);
            for (byte b : bytes) {
                hex.append(String.format("%02X", b));
            }
            return hex.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }
}
