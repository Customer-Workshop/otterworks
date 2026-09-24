package com.otterworks.report.archive;

import com.otterworks.report.archive.ArchiveDocument.ArchiveEvent;
import com.otterworks.report.archive.ArchiveDocument.ArchiveVersion;
import com.otterworks.report.archive.ArchiveDocument.RetentionPolicy;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Template for the two JDBC-backed stores: the document assembly (versions, then the events
 * of those versions, then the policy of each version) is shared; the dialect-specific SQL and
 * row mapping live in the subclasses.
 */
public abstract class JdbcArchiveStore implements ArchiveStore {

    private final JdbcTemplate jdbc;

    protected JdbcArchiveStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    protected abstract String versionsSql();

    protected abstract String eventsSql();

    protected abstract String policySql();

    protected abstract String pingSql();

    protected abstract RowMapper<ArchiveVersion> versionMapper();

    protected abstract RowMapper<ArchiveEvent> eventMapper();

    protected abstract RowMapper<RetentionPolicy> policyMapper();

    /** The parameter value for {@code DOC_ID = ?}; Db2 CHAR(36) compares with padding semantics. */
    protected Object docIdParameter(String docId) {
        return docId;
    }

    @Override
    public Optional<ArchiveDocument> findDocument(String docId) {
        try {
            List<ArchiveVersion> versions = jdbc.query(versionsSql(), versionMapper(), docIdParameter(docId));
            if (versions.isEmpty()) {
                return Optional.empty();
            }
            Map<String, RetentionPolicy> policies = new HashMap<String, RetentionPolicy>();
            for (ArchiveVersion version : versions) {
                List<ArchiveEvent> events = jdbc.query(eventsSql(), eventMapper(), version.raw.archKey);
                for (ArchiveEvent event : events) {
                    event.archKey = null;
                }
                version.events = events;
                String policyCode = version.retentionClass;
                if (!policies.containsKey(policyCode)) {
                    List<RetentionPolicy> found = jdbc.query(policySql(), policyMapper(), policyCode);
                    policies.put(policyCode, found.isEmpty() ? null : found.get(0));
                }
                version.policy = policies.get(policyCode);
            }
            return Optional.of(new ArchiveDocument(Db2Text.rtrim(docId), storeName(), versions));
        } catch (DataAccessException e) {
            throw new ArchiveStoreUnavailableException(storeName() + " archive store query failed", e);
        }
    }

    @Override
    public void ping() {
        try {
            jdbc.queryForObject(pingSql(), Integer.class);
        } catch (DataAccessException e) {
            throw new ArchiveStoreUnavailableException(storeName() + " archive store unreachable", e);
        }
    }

    /** All FILEAUD events of one DOCARCH key (used by the hash endpoint's event section). */
    protected List<ArchiveEvent> eventsOf(String archKey) {
        return new ArrayList<ArchiveEvent>(jdbc.query(eventsSql(), eventMapper(), archKey));
    }
}
