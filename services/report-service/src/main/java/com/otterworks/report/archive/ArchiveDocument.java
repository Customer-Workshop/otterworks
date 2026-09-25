package com.otterworks.report.archive;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Retention history of one archived document, identical from both stores (CONTRACTS §10.4).
 */
@JsonPropertyOrder({"doc_id", "store", "versions"})
public class ArchiveDocument {

    @JsonProperty("doc_id")
    private final String docId;
    @JsonProperty("store")
    private final String store;
    @JsonProperty("versions")
    private final List<ArchiveVersion> versions;
    /** Retired retention code -> active successor (RETNPLCY.SUCCESSOR_CODE), for hashing only. */
    @JsonIgnore
    private final Map<String, String> successorCodes = new HashMap<String, String>();

    public ArchiveDocument(String docId, String store, List<ArchiveVersion> versions) {
        this.docId = docId;
        this.store = store;
        this.versions = versions == null ? new ArrayList<ArchiveVersion>() : versions;
    }

    public String getDocId() {
        return docId;
    }

    public String getStore() {
        return store;
    }

    public List<ArchiveVersion> getVersions() {
        return versions;
    }

    public Map<String, String> getSuccessorCodes() {
        return successorCodes;
    }

    /**
     * Drops the {@code raw} blocks so the default response is byte-identical from both stores
     * (Db2 keeps CHAR padding in raw, Azure SQL does not). Callers opt in with {@code ?raw=true}.
     */
    public ArchiveDocument withoutRaw() {
        for (ArchiveVersion version : versions) {
            version.raw = null;
            for (ArchiveEvent event : version.events) {
                event.raw = null;
            }
        }
        return this;
    }

    /** One DOCARCH row. Display values are right-trimmed; {@code raw} keeps the padded CHAR text. */
    @JsonPropertyOrder({"arch_key", "version_no", "retention_class", "last_access_ts", "storage_charge",
        "unit_rate", "owner_name", "disposition_dt", "legal_hold", "checksum_alg", "content_sha256",
        "byte_size", "source_sys", "policy", "events", "raw"})
    public static class ArchiveVersion {
        @JsonProperty("arch_key")
        public String archKey;
        @JsonProperty("version_no")
        public int versionNo;
        @JsonProperty("retention_class")
        public String retentionClass;
        @JsonProperty("last_access_ts")
        public String lastAccessTs;
        @JsonProperty("storage_charge")
        public String storageCharge;
        @JsonProperty("unit_rate")
        public String unitRate;
        @JsonProperty("owner_name")
        public String ownerName;
        @JsonProperty("disposition_dt")
        public String dispositionDt;
        @JsonProperty("legal_hold")
        public boolean legalHold;
        @JsonProperty("checksum_alg")
        public String checksumAlg;
        @JsonProperty("content_sha256")
        public String contentSha256;
        @JsonProperty("byte_size")
        public long byteSize;
        @JsonProperty("source_sys")
        public String sourceSys;
        @JsonProperty("policy")
        @JsonInclude(JsonInclude.Include.NON_NULL)
        public RetentionPolicy policy;
        @JsonProperty("events")
        public List<ArchiveEvent> events = new ArrayList<ArchiveEvent>();
        @JsonProperty("raw")
        @JsonInclude(JsonInclude.Include.NON_NULL)
        public RawVersion raw = new RawVersion();
    }

    /** Untrimmed CHAR values as read from the store (Db2 keeps the padding; Azure SQL does not). */
    @JsonPropertyOrder({"arch_key", "doc_id", "retention_class", "owner_name", "disposition_dt", "legal_hold_flag"})
    public static class RawVersion {
        @JsonProperty("arch_key")
        public String archKey;
        @JsonProperty("doc_id")
        public String docId;
        @JsonProperty("retention_class")
        public String retentionClass;
        @JsonProperty("owner_name")
        public String ownerName;
        @JsonProperty("disposition_dt")
        public String dispositionDt;
        @JsonProperty("legal_hold_flag")
        public String legalHoldFlag;
    }

    /** One FILEAUD row. */
    @JsonPropertyOrder({"audit_key", "event_type", "event_ts", "actor_id", "retention_class",
        "disposition_code", "client_ip", "detail_text", "raw"})
    public static class ArchiveEvent {
        @JsonProperty("audit_key")
        public String auditKey;
        @JsonProperty("arch_key")
        @JsonInclude(JsonInclude.Include.NON_NULL)
        public String archKey;
        @JsonProperty("event_type")
        public String eventType;
        @JsonProperty("event_ts")
        public String eventTs;
        @JsonProperty("actor_id")
        public String actorId;
        @JsonProperty("retention_class")
        public String retentionClass;
        @JsonProperty("disposition_code")
        public String dispositionCode;
        @JsonProperty("client_ip")
        public String clientIp;
        @JsonProperty("detail_text")
        public String detailText;
        @JsonProperty("raw")
        @JsonInclude(JsonInclude.Include.NON_NULL)
        public RawEvent raw = new RawEvent();
    }

    /** Untrimmed FILEAUD CHAR values. */
    @JsonPropertyOrder({"audit_key", "arch_key", "event_type", "actor_id", "retention_class",
        "disposition_code", "client_ip", "detail_text"})
    public static class RawEvent {
        @JsonProperty("audit_key")
        public String auditKey;
        @JsonProperty("arch_key")
        public String archKey;
        @JsonProperty("event_type")
        public String eventType;
        @JsonProperty("actor_id")
        public String actorId;
        @JsonProperty("retention_class")
        public String retentionClass;
        @JsonProperty("disposition_code")
        public String dispositionCode;
        @JsonProperty("client_ip")
        public String clientIp;
        @JsonProperty("detail_text")
        public String detailText;
    }

    /** One RETNPLCY row (the version's retention class). */
    @JsonPropertyOrder({"policy_code", "policy_desc", "retention_years", "successor_code", "active_flag",
        "disposition_action", "effective_ts"})
    public static class RetentionPolicy {
        @JsonProperty("policy_code")
        public String policyCode;
        @JsonProperty("policy_desc")
        public String policyDesc;
        @JsonProperty("retention_years")
        public int retentionYears;
        @JsonProperty("successor_code")
        public String successorCode;
        @JsonProperty("active_flag")
        public String activeFlag;
        @JsonProperty("disposition_action")
        public String dispositionAction;
        @JsonProperty("effective_ts")
        public String effectiveTs;
    }
}
