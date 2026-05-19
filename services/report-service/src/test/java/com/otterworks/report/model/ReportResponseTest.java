package com.otterworks.report.model;

import org.junit.Test;

import java.util.Date;

import static org.junit.Assert.*;

public class ReportResponseTest {

    @Test
    public void defaultConstructorCreatesEmptyResponse() {
        ReportResponse response = new ReportResponse();
        assertNull(response.getId());
        assertNull(response.getReportName());
    }

    @Test
    public void fromEntityMapsAllFields() {
        Report report = new Report();
        report.setId(42L);
        report.setReportName("Test Report");
        report.setCategory(ReportCategory.USAGE_ANALYTICS);
        report.setReportType(ReportType.PDF);
        report.setStatus(ReportStatus.COMPLETED);
        report.setRequestedBy("user-1");

        Date now = new Date();
        report.setDateFrom(now);
        report.setDateTo(now);
        report.setCreatedAt(now);
        report.setCompletedAt(now);
        report.setFileSizeBytes(2048L);
        report.setRowCount(50);
        report.setFilePath("/reports/test.pdf");

        ReportResponse response = ReportResponse.fromEntity(report);

        assertEquals(Long.valueOf(42L), response.getId());
        assertEquals("Test Report", response.getReportName());
        assertEquals("USAGE_ANALYTICS", response.getCategory());
        assertEquals("PDF", response.getReportType());
        assertEquals("COMPLETED", response.getStatus());
        assertEquals("user-1", response.getRequestedBy());
        assertEquals(now, response.getDateFrom());
        assertEquals(now, response.getDateTo());
        assertEquals(Long.valueOf(2048L), response.getFileSizeBytes());
        assertEquals(Integer.valueOf(50), response.getRowCount());
        assertEquals("/api/v1/reports/42/download", response.getDownloadUrl());
        assertNull(response.getErrorMessage());
    }

    @Test
    public void fromEntityHandlesNullFilePath() {
        Report report = new Report();
        report.setId(1L);
        report.setReportName("No File");
        report.setCategory(ReportCategory.AUDIT_LOG);
        report.setReportType(ReportType.CSV);
        report.setStatus(ReportStatus.PENDING);
        report.setRequestedBy("user-1");
        report.setCreatedAt(new Date());

        ReportResponse response = ReportResponse.fromEntity(report);
        assertNull(response.getDownloadUrl());
    }

    @Test
    public void fromEntityHandlesNullEnums() {
        Report report = new Report();
        report.setId(1L);
        report.setReportName("Partial");
        report.setCreatedAt(new Date());

        ReportResponse response = ReportResponse.fromEntity(report);
        assertNull(response.getCategory());
        assertNull(response.getReportType());
        assertNull(response.getStatus());
    }

    @Test
    public void gettersAndSettersWork() {
        ReportResponse response = new ReportResponse();
        response.setId(99L);
        response.setReportName("Setter Test");
        response.setCategory("USAGE_ANALYTICS");
        response.setReportType("EXCEL");
        response.setStatus("COMPLETED");
        response.setRequestedBy("admin-1");
        response.setFileSizeBytes(4096L);
        response.setRowCount(200);
        response.setDownloadUrl("/download/99");
        response.setErrorMessage("test error");

        assertEquals(Long.valueOf(99L), response.getId());
        assertEquals("Setter Test", response.getReportName());
        assertEquals("USAGE_ANALYTICS", response.getCategory());
        assertEquals("EXCEL", response.getReportType());
        assertEquals("COMPLETED", response.getStatus());
        assertEquals("admin-1", response.getRequestedBy());
        assertEquals(Long.valueOf(4096L), response.getFileSizeBytes());
        assertEquals(Integer.valueOf(200), response.getRowCount());
        assertEquals("/download/99", response.getDownloadUrl());
        assertEquals("test error", response.getErrorMessage());
    }
}
