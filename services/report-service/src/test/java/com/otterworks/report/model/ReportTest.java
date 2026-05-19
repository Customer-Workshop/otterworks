package com.otterworks.report.model;

import org.junit.jupiter.api.Test;

import java.util.Date;

import static org.junit.jupiter.api.Assertions.*;

public class ReportTest {

    @Test
    public void defaultConstructorCreatesEmptyReport() {
        Report report = new Report();
        assertNull(report.getId());
        assertNull(report.getReportName());
        assertNull(report.getCategory());
        assertNull(report.getReportType());
        assertNull(report.getStatus());
    }

    @Test
    public void gettersAndSettersWork() {
        Report report = new Report();
        report.setId(1L);
        report.setReportName("Test Report");
        report.setCategory(ReportCategory.USAGE_ANALYTICS);
        report.setReportType(ReportType.PDF);
        report.setStatus(ReportStatus.PENDING);
        report.setRequestedBy("user-1");

        Date now = new Date();
        report.setDateFrom(now);
        report.setDateTo(now);
        report.setCreatedAt(now);
        report.setCompletedAt(now);
        report.setFilePath("/reports/test.pdf");
        report.setFileSizeBytes(1024L);
        report.setRowCount(100);
        report.setErrorMessage(null);
        report.setParameters("{\"key\":\"value\"}");

        assertEquals(Long.valueOf(1L), report.getId());
        assertEquals("Test Report", report.getReportName());
        assertEquals(ReportCategory.USAGE_ANALYTICS, report.getCategory());
        assertEquals(ReportType.PDF, report.getReportType());
        assertEquals(ReportStatus.PENDING, report.getStatus());
        assertEquals("user-1", report.getRequestedBy());
        assertEquals(now, report.getDateFrom());
        assertEquals(now, report.getDateTo());
        assertEquals(now, report.getCreatedAt());
        assertEquals(now, report.getCompletedAt());
        assertEquals("/reports/test.pdf", report.getFilePath());
        assertEquals(Long.valueOf(1024L), report.getFileSizeBytes());
        assertEquals(Integer.valueOf(100), report.getRowCount());
        assertNull(report.getErrorMessage());
        assertEquals("{\"key\":\"value\"}", report.getParameters());
    }
}
