package com.otterworks.report.archive;

import com.otterworks.report.archive.ArchiveDocument.ArchiveEvent;
import com.otterworks.report.archive.ArchiveDocument.ArchiveVersion;
import com.otterworks.report.archive.ArchiveDocument.RetentionPolicy;
import org.junit.Test;
import org.mockito.ArgumentMatchers;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.Collections;
import java.util.Optional;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/** Assembly logic shared by both stores, exercised against a mocked JdbcTemplate. */
public class JdbcArchiveStoreTest {

    private static ArchiveVersion version(String rawKey, int no) {
        ArchiveVersion v = new ArchiveVersion();
        v.raw.archKey = rawKey;
        v.archKey = Db2Text.rtrim(rawKey);
        v.versionNo = no;
        v.retentionClass = "FIN7";
        return v;
    }

    private static ArchiveEvent event(String key) {
        ArchiveEvent e = new ArchiveEvent();
        e.raw.auditKey = key;
        e.auditKey = key;
        e.archKey = "DA1";
        return e;
    }

    @Test
    public void assemblesVersionsEventsAndPolicy() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(jdbc.query(eq(Db2ArchiveStore.VERSIONS_SQL), ArgumentMatchers.<RowMapper<ArchiveVersion>>any(),
                eq("doc-1"))).thenReturn(Arrays.asList(version("DA1  ", 1), version("DA2  ", 2)));
        when(jdbc.query(eq(Db2ArchiveStore.EVENTS_SQL), ArgumentMatchers.<RowMapper<ArchiveEvent>>any(),
                eq("DA1  "))).thenReturn(Collections.singletonList(event("FA1")));
        when(jdbc.query(eq(Db2ArchiveStore.EVENTS_SQL), ArgumentMatchers.<RowMapper<ArchiveEvent>>any(),
                eq("DA2  "))).thenReturn(Collections.<ArchiveEvent>emptyList());
        RetentionPolicy policy = new RetentionPolicy();
        policy.policyCode = "FIN7";
        when(jdbc.query(eq(Db2ArchiveStore.POLICY_SQL), ArgumentMatchers.<RowMapper<RetentionPolicy>>any(),
                eq("FIN7"))).thenReturn(Collections.singletonList(policy));

        Optional<ArchiveDocument> found = new Db2ArchiveStore(jdbc).findDocument("doc-1");
        assertTrue(found.isPresent());
        ArchiveDocument doc = found.get();
        assertEquals("db2", doc.getStore());
        assertEquals(2, doc.getVersions().size());
        assertEquals(1, doc.getVersions().get(0).events.size());
        assertNull(doc.getVersions().get(0).events.get(0).archKey);
        assertEquals("FIN7", doc.getVersions().get(1).policy.policyCode);
    }

    @Test
    public void noVersionsMeansEmpty() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(jdbc.query(any(String.class), ArgumentMatchers.<RowMapper<ArchiveVersion>>any(), any(Object.class)))
                .thenReturn(Collections.<ArchiveVersion>emptyList());
        assertFalse(new AzureSqlArchiveStore(jdbc).findDocument("doc-1").isPresent());
    }

    @Test
    public void connectionFailureBecomesUnavailable() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(jdbc.query(any(String.class), ArgumentMatchers.<RowMapper<ArchiveVersion>>any(), any(Object.class)))
                .thenThrow(new DataAccessResourceFailureException("down"));
        when(jdbc.queryForObject(any(String.class), eq(Integer.class)))
                .thenThrow(new DataAccessResourceFailureException("down"));
        Db2ArchiveStore store = new Db2ArchiveStore(jdbc);
        try {
            store.findDocument("doc-1");
            fail();
        } catch (ArchiveStoreUnavailableException expected) {
            assertTrue(expected.getMessage().contains("db2"));
        }
        try {
            store.ping();
            fail();
        } catch (ArchiveStoreUnavailableException expected) {
            assertTrue(expected.getMessage().contains("unreachable"));
        }
    }

    @Test
    public void azureRowMapperRebuildsTimestampAndDate() throws SQLException {
        ResultSet rs = mock(ResultSet.class);
        when(rs.getString("ARCH_KEY")).thenReturn("DA00000000000042");
        when(rs.getString("DOC_ID")).thenReturn("doc-1                               ");
        when(rs.getInt("VERSION_NO")).thenReturn(3);
        when(rs.getString("RETENTION_CLASS")).thenReturn("FIN7");
        when(rs.getString("LAST_ACCESS_TS")).thenReturn("2016-03-01 10:15:30.1234567");
        when(rs.getInt("LAST_ACCESS_TS_NANOS_TAIL")).thenReturn(89012);
        when(rs.getBigDecimal("STORAGE_CHARGE")).thenReturn(new java.math.BigDecimal("1234.5"));
        when(rs.getBigDecimal("UNIT_RATE")).thenReturn(new java.math.BigDecimal("0.01"));
        when(rs.getString("OWNER_NAME")).thenReturn("LOPEZ, M.");
        when(rs.getString("DISPOSITION_DT")).thenReturn("2023-03-01");
        when(rs.getString("LEGAL_HOLD_FLAG")).thenReturn("Y");
        when(rs.getString("CHECKSUM_ALG")).thenReturn("SHA256  ");
        when(rs.getString("CONTENT_SHA256")).thenReturn("AB");
        when(rs.getLong("BYTE_SIZE")).thenReturn(4096L);
        when(rs.getString("SOURCE_SYS")).thenReturn("DMS");

        ArchiveVersion v = AzureSqlArchiveStore.mapVersion(rs);
        assertEquals("2016-03-01-10.15.30.123456789012", v.lastAccessTs);
        assertEquals("1234.50000000", v.storageCharge);
        assertEquals("2023-03-01", v.dispositionDt);
        assertEquals("20230301", v.raw.dispositionDt);
        assertTrue(v.legalHold);
        assertEquals("SHA256", v.checksumAlg);
    }

    @Test
    public void postgresRowMapperRebuildsTimestampFromSixPlusSixDigits() throws SQLException {
        ResultSet rs = mock(ResultSet.class);
        when(rs.getString("ARCH_KEY")).thenReturn("DA00000000000042");
        when(rs.getString("DOC_ID")).thenReturn("doc-1                               ");
        when(rs.getInt("VERSION_NO")).thenReturn(3);
        when(rs.getString("RETENTION_CLASS")).thenReturn("FIN7");
        when(rs.getString("LAST_ACCESS_TS")).thenReturn("2016-03-01 10:15:30.123456");
        when(rs.getInt("LAST_ACCESS_TS_NANOS_TAIL")).thenReturn(789012);
        when(rs.getBigDecimal("STORAGE_CHARGE")).thenReturn(new java.math.BigDecimal("1234.5"));
        when(rs.getBigDecimal("UNIT_RATE")).thenReturn(new java.math.BigDecimal("0.01"));
        when(rs.getString("OWNER_NAME")).thenReturn("LOPEZ, M.");
        when(rs.getString("DISPOSITION_DT")).thenReturn("2023-03-01");
        when(rs.getString("LEGAL_HOLD_FLAG")).thenReturn("Y");
        when(rs.getString("CHECKSUM_ALG")).thenReturn("SHA256  ");
        when(rs.getString("CONTENT_SHA256")).thenReturn("AB");
        when(rs.getLong("BYTE_SIZE")).thenReturn(4096L);
        when(rs.getString("SOURCE_SYS")).thenReturn("DMS");

        ArchiveVersion v = PostgresArchiveStore.mapVersion(rs);
        assertEquals("2016-03-01-10.15.30.123456789012", v.lastAccessTs);
        assertEquals("1234.50000000", v.storageCharge);
        assertEquals("2023-03-01", v.dispositionDt);
        assertEquals("20230301", v.raw.dispositionDt);
        assertTrue(v.legalHold);

        ResultSet ev = mock(ResultSet.class);
        when(ev.getString("AUDIT_KEY")).thenReturn("FA000000000000000123");
        when(ev.getString("ARCH_KEY")).thenReturn("DA00000000000042");
        when(ev.getString("EVENT_TYPE")).thenReturn("VIEW");
        when(ev.getString("EVENT_TS")).thenReturn("2015-07-02 08:00:00");
        when(ev.getInt("EVENT_TS_NANOS_TAIL")).thenReturn(1);
        ArchiveEvent e = PostgresArchiveStore.mapEvent(ev);
        assertEquals("2015-07-02-08.00.00.000000000001", e.eventTs);
        assertEquals("postgresql", new PostgresArchiveStore(mock(JdbcTemplate.class)).storeName());
    }

    @Test
    public void pgTimestampHelperMatchesAzureHelperForTheSameInstant() {
        assertEquals(Db2Text.timestamp12FromDateTime2("2016-03-01 10:15:30.1234567", 89012),
                Db2Text.timestamp12FromPgTimestamp("2016-03-01 10:15:30.123456", 789012));
        assertEquals("2016-03-01-10.15.30.100000000000", Db2Text.timestamp12FromPgTimestamp("2016-03-01 10:15:30.1", 0));
        assertNull(Db2Text.timestamp12FromPgTimestamp(null, 0));
    }

    @Test
    public void db2RowMapperDecodesEbcdicAndKeepsPadding() throws Exception {
        ResultSet rs = mock(ResultSet.class);
        when(rs.getString("ARCH_KEY")).thenReturn("DA00000000000042");
        when(rs.getString("DOC_ID")).thenReturn("doc-1                               ");
        when(rs.getInt("VERSION_NO")).thenReturn(3);
        when(rs.getString("RETENTION_CLASS")).thenReturn("FIN7");
        when(rs.getString("LAST_ACCESS_TS")).thenReturn("2016-03-01-10.15.30.123456789012");
        when(rs.getBigDecimal("STORAGE_CHARGE")).thenReturn(new java.math.BigDecimal("1234.50000000"));
        when(rs.getBigDecimal("UNIT_RATE")).thenReturn(new java.math.BigDecimal("0.01000000"));
        when(rs.getBytes("OWNER_NAME")).thenReturn("LOPEZ, M.      ".getBytes("IBM037"));
        when(rs.getBytes("DISPOSITION_DT")).thenReturn("20230301".getBytes("IBM037"));
        when(rs.getString("LEGAL_HOLD_FLAG")).thenReturn("N");
        when(rs.getString("CHECKSUM_ALG")).thenReturn("SHA256  ");
        when(rs.getString("CONTENT_SHA256")).thenReturn("AB");
        when(rs.getLong("BYTE_SIZE")).thenReturn(4096L);
        when(rs.getString("SOURCE_SYS")).thenReturn("DMS");

        ArchiveVersion v = Db2ArchiveStore.mapVersion(rs);
        assertEquals("LOPEZ, M.", v.ownerName);
        assertEquals("LOPEZ, M.      ", v.raw.ownerName);
        assertEquals("2023-03-01", v.dispositionDt);
        assertEquals("2016-03-01-10.15.30.123456789012", v.lastAccessTs);
        assertFalse(v.legalHold);
    }
}
