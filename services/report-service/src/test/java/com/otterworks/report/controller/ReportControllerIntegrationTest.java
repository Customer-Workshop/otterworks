package com.otterworks.report.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.otterworks.report.model.ReportCategory;
import com.otterworks.report.model.ReportRequest;
import com.otterworks.report.model.ReportType;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit4.SpringRunner;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Date;

import static org.junit.Assert.assertEquals;
import static org.hamcrest.Matchers.anyOf;
import static org.hamcrest.Matchers.everyItem;
import static org.hamcrest.Matchers.is;
import static org.hamcrest.Matchers.notNullValue;
import static org.hamcrest.Matchers.nullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Integration tests for {@link ReportController} REST endpoints.
 *
 * Verifies HTTP status codes, content types, and response body structure
 * for every controller action. Uses a real Spring context with an H2
 * in-memory database (profile "test").
 *
 * Caller identity is supplied the way the API gateway does it in production:
 * via the {@code X-User-ID} header set after JWT validation.
 *
 * Written in JUnit 4 style to match the current stack. After the JUnit 5
 * migration (Axis 4), replace:
 *   - @RunWith(SpringRunner.class) -> remove
 *   - org.junit.Test              -> org.junit.jupiter.api.Test
 */
@RunWith(SpringRunner.class)
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
public class ReportControllerIntegrationTest {

    private static final String USER_ID_HEADER = "X-User-ID";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    // ---- POST /api/v1/reports ----

    @Test
    public void createPdfReportReturns202WithCorrectBody() throws Exception {
        ReportRequest request = buildRequest("Integration PDF Report",
                ReportCategory.USAGE_ANALYTICS, ReportType.PDF);

        mockMvc.perform(post("/api/v1/reports")
                        .header(USER_ID_HEADER, "integration-user-1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isAccepted())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id", notNullValue()))
                .andExpect(jsonPath("$.reportName", is("Integration PDF Report")))
                .andExpect(jsonPath("$.category", is("USAGE_ANALYTICS")))
                .andExpect(jsonPath("$.reportType", is("PDF")))
                .andExpect(jsonPath("$.requestedBy", is("integration-user-1")))
                .andExpect(jsonPath("$.status",
                        anyOf(is("PENDING"), is("GENERATING"), is("COMPLETED"))));
    }

    @Test
    public void createCsvReportReturns202() throws Exception {
        ReportRequest request = buildRequest("Integration CSV Report",
                ReportCategory.AUDIT_LOG, ReportType.CSV);

        mockMvc.perform(post("/api/v1/reports")
                        .header(USER_ID_HEADER, "integration-user-2")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.reportType", is("CSV")))
                .andExpect(jsonPath("$.category", is("AUDIT_LOG")));
    }

    @Test
    public void createExcelReportReturns202() throws Exception {
        ReportRequest request = buildRequest("Integration Excel Report",
                ReportCategory.STORAGE_SUMMARY, ReportType.EXCEL);

        mockMvc.perform(post("/api/v1/reports")
                        .header(USER_ID_HEADER, "integration-user-3")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.reportType", is("EXCEL")))
                .andExpect(jsonPath("$.category", is("STORAGE_SUMMARY")));
    }

    @Test
    public void createReportWithoutNameReturns400() throws Exception {
        ReportRequest request = new ReportRequest();
        request.setCategory(ReportCategory.COMPLIANCE);
        request.setReportType(ReportType.PDF);

        mockMvc.perform(post("/api/v1/reports")
                        .header(USER_ID_HEADER, "integration-user-4")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    public void createReportWithoutCategoryReturns400() throws Exception {
        ReportRequest request = new ReportRequest();
        request.setReportName("Missing Category Report");
        request.setReportType(ReportType.CSV);

        mockMvc.perform(post("/api/v1/reports")
                        .header(USER_ID_HEADER, "integration-user-5")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    public void createReportWithoutTypeReturns400() throws Exception {
        ReportRequest request = new ReportRequest();
        request.setReportName("Missing Type Report");
        request.setCategory(ReportCategory.USER_ACTIVITY);

        mockMvc.perform(post("/api/v1/reports")
                        .header(USER_ID_HEADER, "integration-user-6")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    public void createReportWithoutIdentityReturns401() throws Exception {
        ReportRequest request = buildRequest("Anonymous Report",
                ReportCategory.USAGE_ANALYTICS, ReportType.PDF);

        mockMvc.perform(post("/api/v1/reports")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    public void createReportIgnoresClientSuppliedRequestedBy() throws Exception {
        ReportRequest request = buildRequest("Spoofed Owner Report",
                ReportCategory.USAGE_ANALYTICS, ReportType.PDF);
        request.setRequestedBy("victim-user");

        mockMvc.perform(post("/api/v1/reports")
                        .header(USER_ID_HEADER, "integration-user-10")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.requestedBy", is("integration-user-10")));
    }

    // ---- GET /api/v1/reports/{id} ----

    @Test
    public void getReportByIdReturnsCreatedReport() throws Exception {
        Long id = createReportAndReturnId("Fetch By Id Report",
                ReportCategory.SYSTEM_HEALTH, ReportType.PDF, "integration-user-7");

        mockMvc.perform(get("/api/v1/reports/" + id)
                        .header(USER_ID_HEADER, "integration-user-7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id", is(id.intValue())))
                .andExpect(jsonPath("$.reportName", is("Fetch By Id Report")))
                .andExpect(jsonPath("$.category", is("SYSTEM_HEALTH")));
    }

    @Test
    public void getNonExistentReportReturns404() throws Exception {
        mockMvc.perform(get("/api/v1/reports/999999")
                        .header(USER_ID_HEADER, "integration-user-7"))
                .andExpect(status().isNotFound());
    }

    @Test
    public void getReportWithoutIdentityReturns401() throws Exception {
        Long id = createReportAndReturnId("Anonymous Fetch Report",
                ReportCategory.SYSTEM_HEALTH, ReportType.PDF, "integration-user-7");

        mockMvc.perform(get("/api/v1/reports/" + id))
                .andExpect(status().isUnauthorized());
    }

    @Test
    public void getReportOwnedByAnotherUserReturns404() throws Exception {
        Long id = createReportAndReturnId("Victim Report",
                ReportCategory.SYSTEM_HEALTH, ReportType.PDF, "idor-victim");

        mockMvc.perform(get("/api/v1/reports/" + id)
                        .header(USER_ID_HEADER, "idor-attacker"))
                .andExpect(status().isNotFound());
    }

    // ---- GET /api/v1/reports ----

    @Test
    public void listReportsReturnsOnlyCallersReports() throws Exception {
        String userId = "list-test-user-" + System.currentTimeMillis();
        createReportAndReturnId("List Test 1", ReportCategory.AUDIT_LOG,
                ReportType.CSV, userId);
        createReportAndReturnId("List Test 2", ReportCategory.AUDIT_LOG,
                ReportType.PDF, userId);
        createReportAndReturnId("Someone Else's Report", ReportCategory.AUDIT_LOG,
                ReportType.PDF, userId + "-other");

        mockMvc.perform(get("/api/v1/reports")
                        .header(USER_ID_HEADER, userId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reports").isArray())
                .andExpect(jsonPath("$.total", is(2)))
                .andExpect(jsonPath("$.reports[*].requestedBy", everyItem(is(userId))));
    }

    @Test
    public void listReportsIgnoresClientSuppliedUserId() throws Exception {
        String victim = "list-victim-" + System.currentTimeMillis();
        createReportAndReturnId("Victim List Report", ReportCategory.AUDIT_LOG,
                ReportType.CSV, victim);

        mockMvc.perform(get("/api/v1/reports")
                        .header(USER_ID_HEADER, "list-attacker")
                        .param("userId", victim))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reports").isArray())
                .andExpect(jsonPath("$.total", is(0)));
    }

    @Test
    public void listReportsForUnknownUserReturnsEmptyArray() throws Exception {
        mockMvc.perform(get("/api/v1/reports")
                        .header(USER_ID_HEADER, "nonexistent-user-xyz"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reports").isArray())
                .andExpect(jsonPath("$.total", is(0)));
    }

    @Test
    public void listReportsByStatusReturnsArray() throws Exception {
        mockMvc.perform(get("/api/v1/reports")
                        .header(USER_ID_HEADER, "integration-user-7")
                        .param("status", "COMPLETED"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reports").isArray());
    }

    @Test
    public void listReportsWithoutIdentityReturns401() throws Exception {
        mockMvc.perform(get("/api/v1/reports"))
                .andExpect(status().isUnauthorized());
    }

    // ---- GET /api/v1/reports/{id}/download ----

    @Test
    public void downloadNonExistentReportReturns404() throws Exception {
        mockMvc.perform(get("/api/v1/reports/999999/download")
                        .header(USER_ID_HEADER, "integration-user-8"))
                .andExpect(status().isNotFound());
    }

    @Test
    public void downloadReportOwnedByAnotherUserReturns404() throws Exception {
        Long id = createReportAndReturnId("Victim Download Report",
                ReportCategory.USAGE_ANALYTICS, ReportType.CSV, "idor-victim");

        mockMvc.perform(get("/api/v1/reports/" + id + "/download")
                        .header(USER_ID_HEADER, "idor-attacker"))
                .andExpect(status().isNotFound());
    }

    @Test
    public void downloadReportWithoutIdentityReturns401() throws Exception {
        Long id = createReportAndReturnId("Anonymous Download Report",
                ReportCategory.USAGE_ANALYTICS, ReportType.CSV, "integration-user-8");

        mockMvc.perform(get("/api/v1/reports/" + id + "/download"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    public void downloadPendingReportReturns409() throws Exception {
        Long id = createReportAndReturnId("Download Pending Report",
                ReportCategory.USAGE_ANALYTICS, ReportType.PDF, "integration-user-8");

        MvcResult download = mockMvc.perform(get("/api/v1/reports/" + id + "/download")
                        .header(USER_ID_HEADER, "integration-user-8"))
                .andReturn();

        // Status is read after the download so it cannot go stale in the wrong direction:
        // generation only moves forward, so a report still pending here was pending during
        // the download too.
        MvcResult result = mockMvc.perform(get("/api/v1/reports/" + id)
                        .header(USER_ID_HEADER, "integration-user-8"))
                .andReturn();
        String statusVal = objectMapper.readTree(
                result.getResponse().getContentAsString()).get("status").asText();

        if ("PENDING".equals(statusVal) || "GENERATING".equals(statusVal)) {
            assertEquals(HttpStatus.CONFLICT.value(), download.getResponse().getStatus());
        }
    }

    // ---- DELETE /api/v1/reports/{id} ----

    @Test
    public void deleteExistingReportReturns204() throws Exception {
        Long id = createReportAndReturnId("Delete Me Report",
                ReportCategory.COLLABORATION_METRICS, ReportType.CSV, "integration-user-9");

        mockMvc.perform(delete("/api/v1/reports/" + id)
                        .header(USER_ID_HEADER, "integration-user-9"))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/api/v1/reports/" + id)
                        .header(USER_ID_HEADER, "integration-user-9"))
                .andExpect(status().isNotFound());
    }

    @Test
    public void deleteNonExistentReportReturns404() throws Exception {
        mockMvc.perform(delete("/api/v1/reports/999999")
                        .header(USER_ID_HEADER, "integration-user-9"))
                .andExpect(status().isNotFound());
    }

    @Test
    public void deleteReportOwnedByAnotherUserReturns404AndKeepsReport() throws Exception {
        Long id = createReportAndReturnId("Victim Delete Report",
                ReportCategory.COLLABORATION_METRICS, ReportType.CSV, "idor-victim");

        mockMvc.perform(delete("/api/v1/reports/" + id)
                        .header(USER_ID_HEADER, "idor-attacker"))
                .andExpect(status().isNotFound());

        mockMvc.perform(get("/api/v1/reports/" + id)
                        .header(USER_ID_HEADER, "idor-victim"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id", is(id.intValue())));
    }

    @Test
    public void deleteReportWithoutIdentityReturns401() throws Exception {
        Long id = createReportAndReturnId("Anonymous Delete Report",
                ReportCategory.COLLABORATION_METRICS, ReportType.CSV, "integration-user-9");

        mockMvc.perform(delete("/api/v1/reports/" + id))
                .andExpect(status().isUnauthorized());

        mockMvc.perform(get("/api/v1/reports/" + id)
                        .header(USER_ID_HEADER, "integration-user-9"))
                .andExpect(status().isOk());
    }

    // ---- Health endpoint ----

    @Test
    public void healthEndpointReturnsServiceMetadata() throws Exception {
        mockMvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status", is("healthy")))
                .andExpect(jsonPath("$.service", is("report-service")))
                .andExpect(jsonPath("$.version", is("0.1.0")));
    }

    // ---- Helpers ----

    private ReportRequest buildRequest(String name, ReportCategory category,
                                       ReportType type) {
        ReportRequest request = new ReportRequest();
        request.setReportName(name);
        request.setCategory(category);
        request.setReportType(type);
        request.setDateFrom(new Date(System.currentTimeMillis() - 86400000L * 7));
        request.setDateTo(new Date());
        return request;
    }

    private Long createReportAndReturnId(String name, ReportCategory category,
                                         ReportType type, String ownerUserId) throws Exception {
        ReportRequest request = buildRequest(name, category, type);
        MvcResult result = mockMvc.perform(post("/api/v1/reports")
                        .header(USER_ID_HEADER, ownerUserId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isAccepted())
                .andReturn();

        String body = result.getResponse().getContentAsString();
        return objectMapper.readTree(body).get("id").asLong();
    }
}
