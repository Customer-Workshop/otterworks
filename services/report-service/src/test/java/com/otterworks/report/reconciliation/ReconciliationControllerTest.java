package com.otterworks.report.reconciliation;

import com.otterworks.report.archive.ArchiveExceptionHandler;
import com.otterworks.report.archive.ArchiveStoreType;
import com.otterworks.report.archive.ArchiveStoreUnavailableException;
import com.otterworks.report.reconciliation.ReconciliationReport.ClassTotalRow;
import com.otterworks.report.reconciliation.ReconciliationReport.FailureRow;
import com.otterworks.report.reconciliation.ReconciliationReport.RunSummary;
import com.otterworks.report.reconciliation.ReconciliationReport.SessionLink;
import com.otterworks.report.reconciliation.ReconciliationReport.TableRow;
import org.junit.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Collections;
import java.util.Optional;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

public class ReconciliationControllerTest {

    private static MockMvc mvcFor(ReconciliationRepository repository) {
        return MockMvcBuilders.standaloneSetup(new ReconciliationController(repository))
                .setControllerAdvice(new ArchiveExceptionHandler())
                .build();
    }

    private static ReconciliationRepository repositoryFor(ArchiveStoreType type) {
        ReconciliationRepository repository = mock(ReconciliationRepository.class);
        when(repository.storeType()).thenReturn(type);
        when(repository.isAvailable()).thenReturn(type == ArchiveStoreType.AZURESQL);
        when(repository.namespace()).thenReturn("d24-after");
        return repository;
    }

    @Test
    public void db2DeploymentHasNoMigration() throws Exception {
        MockMvc mvc = mvcFor(repositoryFor(ArchiveStoreType.DB2));
        mvc.perform(get("/api/reports/reconciliation"))
                .andExpect(status().isNotFound())
                .andExpect(content().json("{\"error\":\"no migration in this namespace\"}"));
        mvc.perform(get("/api/v1/reports/reconciliation/r1.csv"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("no migration in this namespace"));
    }

    @Test
    public void featureOffKeeps404WithHint() throws Exception {
        MockMvc mvc = mvcFor(repositoryFor(ArchiveStoreType.OFF));
        mvc.perform(get("/api/reports/reconciliation/latest"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("no migration in this namespace"))
                .andExpect(jsonPath("$.hint").value(containsString("ARCHIVE_STORE")));
    }

    @Test
    public void unsupportedStoreReturns503() throws Exception {
        ReconciliationRepository repository = repositoryFor(ArchiveStoreType.INVALID);
        when(repository.listRuns()).thenThrow(new ArchiveStoreUnavailableException("unsupported value"));
        mvcFor(repository).perform(get("/api/reports/reconciliation"))
                .andExpect(status().isServiceUnavailable());
    }

    @Test
    public void unknownRunReturns404() throws Exception {
        ReconciliationRepository repository = repositoryFor(ArchiveStoreType.AZURESQL);
        when(repository.findRun("nope")).thenReturn(Optional.<ReconciliationReport>empty());
        mvcFor(repository).perform(get("/api/reports/reconciliation/nope"))
                .andExpect(status().isNotFound())
                .andExpect(content().json("{\"error\":\"run not found\"}"));
    }

    @Test
    public void latestResolvesNewestRunAndListsRuns() throws Exception {
        ReconciliationRepository repository = repositoryFor(ArchiveStoreType.AZURESQL);
        RunSummary newest = new RunSummary();
        newest.runId = "r20260924150000";
        newest.closes = true;
        RunSummary older = new RunSummary();
        older.runId = "r20260923000000";
        when(repository.listRuns()).thenReturn(Arrays.asList(newest, older));
        when(repository.findRun("r20260924150000")).thenReturn(Optional.of(sample()));
        MockMvc mvc = mvcFor(repository);
        mvc.perform(get("/api/reports/reconciliation"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].run_id").value("r20260924150000"))
                .andExpect(jsonPath("$[1].run_id").value("r20260923000000"));
        mvc.perform(get("/api/v1/reports/reconciliation/latest"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run_id").value("r20260924150000"))
                .andExpect(jsonPath("$.namespace").value("d24-after"))
                .andExpect(jsonPath("$.generated_at").value(containsString("T")))
                .andExpect(jsonPath("$.tables[1].failed").value(37))
                .andExpect(jsonPath("$.failures[0].source_key").value("MIG01-0000000001"))
                .andExpect(jsonPath("$.failures[0].sqlstate").doesNotExist())
                .andExpect(jsonPath("$.class_totals[0].class").value("FIN7"))
                .andExpect(jsonPath("$.sessions[0].url").value("https://example.invalid/s/1"))
                .andExpect(jsonPath("$.closes").value(true))
                .andExpect(content().string(startsWith("{\"run_id\":\"r20260924150000\",\"namespace\":")));
    }

    @Test
    public void csvMatchesContractShape() throws Exception {
        ReconciliationRepository repository = repositoryFor(ArchiveStoreType.AZURESQL);
        when(repository.findRun("r1")).thenReturn(Optional.of(sample()));
        MvcResult result = mvcFor(repository).perform(get("/api/reports/reconciliation/r1.csv"))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Disposition",
                        "attachment; filename=\"reconciliation-r20260924150000.csv\""))
                .andExpect(content().contentTypeCompatibleWith("text/csv"))
                .andReturn();
        String csv = new String(result.getResponse().getContentAsByteArray(), StandardCharsets.UTF_8);
        String expected = "section,table,extracted,loaded,validated,purged,failed\r\n"
                + "summary,RETNPLCY,40,40,40,0,0\r\n"
                + "summary,DOCARCH,180000,179980,179963,179963,37\r\n"
                + "\r\n"
                + "section,table,source_key,rule,stage,field,sqlstate,error\r\n"
                + "failure,DOCARCH,MIG01-0000000001,CCSID_UNMAPPABLE,LOAD,OWNER_NAME,,"
                + "CCSID037 byte X'3F' at offset 6\r\n"
                + "failure,DOCARCH,MIG07-0000000001,CLASS_TOTAL_MISMATCH,VALIDATE,STORAGE_CHARGE,,"
                + "\"class FIN7 sum differs: 10.00000000 vs 9.00000000, \"\"table\"\" total agrees\"\r\n";
        assertEquals(expected, csv);
    }

    @Test
    public void htmlRendersSummaryClassTotalsFailuresAndSessions() throws Exception {
        ReconciliationRepository repository = repositoryFor(ArchiveStoreType.AZURESQL);
        when(repository.findRun("r1")).thenReturn(Optional.of(sample()));
        MvcResult result = mvcFor(repository).perform(get("/api/reports/reconciliation/r1.html"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith("text/html"))
                .andReturn();
        String html = result.getResponse().getContentAsString();
        assertTrue(html.contains("<td>DOCARCH</td><td class=\"num\">180000</td>"));
        assertTrue(html.contains("badge ok"));
        assertTrue(html.contains("<tr class=\"mig07\">"));
        assertTrue(html.contains("MIG-07 mismatch"));
        assertTrue(html.contains("CCSID_UNMAPPABLE"));
        assertTrue(html.contains("<a href=\"https://example.invalid/s/1\""));
        assertTrue(html.contains("&lt;script&gt;"));
        assertTrue(html.contains("href=\"r20260924150000.csv\""));
    }

    static ReconciliationReport sample() {
        ReconciliationReport r = new ReconciliationReport();
        r.runId = "r20260924150000";
        r.namespace = "d24-after";
        r.status = "SUCCEEDED";
        r.startedAt = "2026-09-24T15:00:00Z";
        r.closes = true;
        TableRow t1 = new TableRow();
        t1.table = "RETNPLCY";
        t1.extracted = 40;
        t1.loaded = 40;
        t1.validated = 40;
        t1.closes = true;
        TableRow t2 = new TableRow();
        t2.table = "DOCARCH";
        t2.extracted = 180000;
        t2.loaded = 179980;
        t2.validated = 179963;
        t2.purged = 179963;
        t2.failed = 37;
        t2.rejected = 20;
        t2.validateFailed = 17;
        t2.closes = true;
        r.tables = Arrays.asList(t1, t2);
        FailureRow f1 = new FailureRow();
        f1.table = "DOCARCH";
        f1.sourceKey = "MIG01-0000000001";
        f1.rule = "CCSID_UNMAPPABLE";
        f1.stage = "LOAD";
        f1.field = "OWNER_NAME";
        f1.error = "CCSID037 byte X'3F' at offset 6";
        f1.issue = "MIG-01";
        FailureRow f2 = new FailureRow();
        f2.table = "DOCARCH";
        f2.sourceKey = "MIG07-0000000001";
        f2.rule = "CLASS_TOTAL_MISMATCH";
        f2.stage = "VALIDATE";
        f2.field = "STORAGE_CHARGE";
        f2.error = "class FIN7 sum differs: 10.00000000 vs 9.00000000, \"table\" total agrees";
        f2.issue = "MIG-07";
        r.failures = Arrays.asList(f1, f2);
        ClassTotalRow c = new ClassTotalRow();
        c.table = "DOCARCH";
        c.retentionClass = "FIN7";
        c.sourceCount = 10;
        c.targetCount = 10;
        c.sourceSum = "10.00000000";
        c.targetSum = "9.00000000";
        c.matches = false;
        r.classTotals = Collections.singletonList(c);
        r.sessions = Collections.singletonList(new SessionLink("app: <script>", "https://example.invalid/s/1"));
        return r;
    }
}
