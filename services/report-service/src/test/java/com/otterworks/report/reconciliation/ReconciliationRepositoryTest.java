package com.otterworks.report.reconciliation;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.sql.Timestamp;
import java.util.TimeZone;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

public class ReconciliationRepositoryTest {

    private TimeZone original;

    @BeforeEach
    public void pinNonUtcZone() {
        original = TimeZone.getDefault();
        TimeZone.setDefault(TimeZone.getTimeZone("America/New_York"));
    }

    @AfterEach
    public void restoreZone() {
        TimeZone.setDefault(original);
    }

    @Test
    public void isoUtcKeepsLedgerWallClockOnNonUtcJvm() {
        Timestamp ts = Timestamp.valueOf("2026-09-24 15:00:00");
        assertEquals("2026-09-24T15:00:00Z", ReconciliationRepository.isoUtc(ts));
        assertNull(ReconciliationRepository.isoUtc(null));
    }

    @Test
    public void issueOfReadsSeededRegisterId() {
        assertEquals("MIG-07", ReconciliationRepository.issueOf("MIG07-0000000001"));
        assertNull(ReconciliationRepository.issueOf("DA00000000000042"));
    }
}
