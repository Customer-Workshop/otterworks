package com.otterworks.report.archive;

import com.otterworks.report.archive.ArchiveDocument.ArchiveEvent;
import com.otterworks.report.archive.ArchiveDocument.ArchiveVersion;
import com.otterworks.report.archive.ArchiveDocument.RetentionPolicy;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.sql.ResultSet;
import java.sql.SQLException;

/**
 * Reads {@code ARCHIVE.*} on Db2 through {@code com.ibm.db2.jcc}.
 *
 * No {@code RTRIM} in SQL: CHAR values arrive padded and are trimmed only in the DTO, with the
 * padded text kept under {@code raw}. {@code FOR BIT DATA} columns are read as bytes and decoded
 * from CCSID 037.
 */
public class Db2ArchiveStore extends JdbcArchiveStore {

    static final String VERSIONS_SQL =
            "SELECT ARCH_KEY, DOC_ID, VERSION_NO, RETENTION_CLASS, CHAR(LAST_ACCESS_TS) AS LAST_ACCESS_TS, "
            + "STORAGE_CHARGE, UNIT_RATE, OWNER_NAME, DISPOSITION_DT, LEGAL_HOLD_FLAG, CHECKSUM_ALG, "
            + "CONTENT_SHA256, BYTE_SIZE, SOURCE_SYS "
            + "FROM ARCHIVE.DOCARCH WHERE DOC_ID = ? ORDER BY VERSION_NO";

    static final String EVENTS_SQL =
            "SELECT AUDIT_KEY, ARCH_KEY, EVENT_TYPE, CHAR(EVENT_TS) AS EVENT_TS, ACTOR_ID, RETENTION_CLASS, "
            + "DISPOSITION_CODE, CLIENT_IP, DETAIL_TEXT "
            + "FROM ARCHIVE.FILEAUD WHERE ARCH_KEY = ? ORDER BY EVENT_TS, AUDIT_KEY";

    static final String POLICY_SQL =
            "SELECT POLICY_CODE, POLICY_DESC, RETENTION_YEARS, SUCCESSOR_CODE, ACTIVE_FLAG, DISPOSITION_ACTION, "
            + "CHAR(EFFECTIVE_TS) AS EFFECTIVE_TS FROM ARCHIVE.RETNPLCY WHERE POLICY_CODE = ?";

    static final String PING_SQL = "SELECT 1 FROM SYSIBM.SYSDUMMY1";

    public Db2ArchiveStore(JdbcTemplate jdbc) {
        super(jdbc);
    }

    @Override
    public String storeName() {
        return ArchiveStoreType.DB2.wireName();
    }

    @Override
    protected String versionsSql() {
        return VERSIONS_SQL;
    }

    @Override
    protected String eventsSql() {
        return EVENTS_SQL;
    }

    @Override
    protected String policySql() {
        return POLICY_SQL;
    }

    @Override
    protected String pingSql() {
        return PING_SQL;
    }

    @Override
    protected RowMapper<ArchiveVersion> versionMapper() {
        return new RowMapper<ArchiveVersion>() {
            @Override
            public ArchiveVersion mapRow(ResultSet rs, int rowNum) throws SQLException {
                return mapVersion(rs);
            }
        };
    }

    @Override
    protected RowMapper<ArchiveEvent> eventMapper() {
        return new RowMapper<ArchiveEvent>() {
            @Override
            public ArchiveEvent mapRow(ResultSet rs, int rowNum) throws SQLException {
                return mapEvent(rs);
            }
        };
    }

    @Override
    protected RowMapper<RetentionPolicy> policyMapper() {
        return new RowMapper<RetentionPolicy>() {
            @Override
            public RetentionPolicy mapRow(ResultSet rs, int rowNum) throws SQLException {
                RetentionPolicy p = new RetentionPolicy();
                p.policyCode = Db2Text.rtrim(rs.getString("POLICY_CODE"));
                p.policyDesc = Db2Text.rtrim(rs.getString("POLICY_DESC"));
                p.retentionYears = rs.getInt("RETENTION_YEARS");
                p.successorCode = Db2Text.rtrim(rs.getString("SUCCESSOR_CODE"));
                p.activeFlag = Db2Text.rtrim(rs.getString("ACTIVE_FLAG"));
                p.dispositionAction = Db2Text.rtrim(rs.getString("DISPOSITION_ACTION"));
                p.effectiveTs = Db2Text.timestamp12FromJdbc(rs.getString("EFFECTIVE_TS"));
                return p;
            }
        };
    }

    static ArchiveVersion mapVersion(ResultSet rs) throws SQLException {
        ArchiveVersion v = new ArchiveVersion();
        v.raw.archKey = rs.getString("ARCH_KEY");
        v.raw.docId = rs.getString("DOC_ID");
        v.raw.retentionClass = rs.getString("RETENTION_CLASS");
        v.raw.ownerName = Db2Text.decodeCp037(rs.getBytes("OWNER_NAME"));
        v.raw.dispositionDt = Db2Text.decodeCp037(rs.getBytes("DISPOSITION_DT"));
        v.raw.legalHoldFlag = rs.getString("LEGAL_HOLD_FLAG");

        v.archKey = Db2Text.rtrim(v.raw.archKey);
        v.versionNo = rs.getInt("VERSION_NO");
        v.retentionClass = Db2Text.rtrim(v.raw.retentionClass);
        v.lastAccessTs = Db2Text.timestamp12FromJdbc(rs.getString("LAST_ACCESS_TS"));
        v.storageCharge = Db2Text.decimal8(rs.getBigDecimal("STORAGE_CHARGE"));
        v.unitRate = Db2Text.decimal8(rs.getBigDecimal("UNIT_RATE"));
        v.ownerName = Db2Text.rtrim(v.raw.ownerName);
        v.dispositionDt = Db2Text.isoDateFromYyyymmdd(v.raw.dispositionDt);
        v.legalHold = "Y".equals(Db2Text.rtrim(v.raw.legalHoldFlag));
        v.checksumAlg = Db2Text.rtrim(rs.getString("CHECKSUM_ALG"));
        v.contentSha256 = Db2Text.rtrim(rs.getString("CONTENT_SHA256"));
        v.byteSize = rs.getLong("BYTE_SIZE");
        v.sourceSys = Db2Text.rtrim(rs.getString("SOURCE_SYS"));
        return v;
    }

    static ArchiveEvent mapEvent(ResultSet rs) throws SQLException {
        ArchiveEvent e = new ArchiveEvent();
        e.raw.auditKey = rs.getString("AUDIT_KEY");
        e.raw.archKey = rs.getString("ARCH_KEY");
        e.raw.eventType = rs.getString("EVENT_TYPE");
        e.raw.actorId = rs.getString("ACTOR_ID");
        e.raw.retentionClass = rs.getString("RETENTION_CLASS");
        e.raw.dispositionCode = rs.getString("DISPOSITION_CODE");
        e.raw.clientIp = rs.getString("CLIENT_IP");
        e.raw.detailText = rs.getString("DETAIL_TEXT");

        e.auditKey = Db2Text.rtrim(e.raw.auditKey);
        e.archKey = Db2Text.rtrim(e.raw.archKey);
        e.eventType = Db2Text.rtrim(e.raw.eventType);
        e.eventTs = Db2Text.timestamp12FromJdbc(rs.getString("EVENT_TS"));
        e.actorId = Db2Text.rtrim(e.raw.actorId);
        e.retentionClass = Db2Text.rtrim(e.raw.retentionClass);
        e.dispositionCode = Db2Text.rtrim(e.raw.dispositionCode);
        e.clientIp = Db2Text.rtrim(e.raw.clientIp);
        e.detailText = Db2Text.rtrim(e.raw.detailText);
        return e;
    }
}
