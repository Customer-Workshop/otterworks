package com.otterworks.report.model;

import org.junit.Test;

import java.util.Date;
import java.util.HashMap;
import java.util.Map;

import static org.junit.Assert.*;

public class ReportRequestTest {

    @Test
    public void defaultConstructorCreatesEmptyRequest() {
        ReportRequest request = new ReportRequest();
        assertNull(request.getReportName());
        assertNull(request.getCategory());
        assertNull(request.getReportType());
        assertNull(request.getRequestedBy());
    }

    @Test
    public void gettersAndSettersWork() {
        ReportRequest request = new ReportRequest();
        request.setReportName("Monthly Report");
        request.setCategory(ReportCategory.AUDIT_LOG);
        request.setReportType(ReportType.CSV);
        request.setRequestedBy("admin-1");

        Date from = new Date();
        Date to = new Date();
        request.setDateFrom(from);
        request.setDateTo(to);

        Map<String, String> params = new HashMap<>();
        params.put("metric", "login_count");
        request.setParameters(params);

        assertEquals("Monthly Report", request.getReportName());
        assertEquals(ReportCategory.AUDIT_LOG, request.getCategory());
        assertEquals(ReportType.CSV, request.getReportType());
        assertEquals("admin-1", request.getRequestedBy());
        assertEquals(from, request.getDateFrom());
        assertEquals(to, request.getDateTo());
        assertEquals("login_count", request.getParameters().get("metric"));
    }
}
