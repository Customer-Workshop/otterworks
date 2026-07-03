package com.otterworks.report.service;

import com.otterworks.report.config.AppConfig;
import com.otterworks.report.model.Report;
import com.otterworks.report.model.ReportCategory;
import com.otterworks.report.model.ReportRequest;
import com.otterworks.report.model.ReportStatus;
import com.otterworks.report.model.ReportType;
import com.otterworks.report.repository.ReportRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Pure unit tests for {@link ReportService} using Mockito mocks
 * (no Spring context).
 */
@ExtendWith(MockitoExtension.class)
public class ReportServiceUnitTest {

    @Mock
    private ReportRepository reportRepository;

    @Mock
    private ReportGenerationWorker generationWorker;

    @Mock
    private AppConfig appConfig;

    private ReportService reportService;

    @BeforeEach
    public void setUp() {
        reportService = new ReportService(reportRepository, generationWorker, appConfig);
        TransactionSynchronizationManager.initSynchronization();
    }

    @AfterEach
    public void tearDown() {
        TransactionSynchronizationManager.clearSynchronization();
    }

    private ReportRequest buildRequest() {
        ReportRequest request = new ReportRequest();
        request.setReportName("Unit Test Report");
        request.setCategory(ReportCategory.USAGE_ANALYTICS);
        request.setReportType(ReportType.PDF);
        request.setRequestedBy("unit-test-user");
        return request;
    }

    @Test
    public void createReportPersistsPendingReportWithDefaults() {
        when(reportRepository.save(any(Report.class))).thenAnswer(inv -> {
            Report r = inv.getArgument(0);
            r.setId(42L);
            return r;
        });

        Report saved = reportService.createReport(buildRequest());

        ArgumentCaptor<Report> captor = ArgumentCaptor.forClass(Report.class);
        verify(reportRepository).save(captor.capture());
        Report persisted = captor.getValue();

        assertEquals("Unit Test Report", persisted.getReportName());
        assertEquals(ReportCategory.USAGE_ANALYTICS, persisted.getCategory());
        assertEquals(ReportType.PDF, persisted.getReportType());
        assertEquals(ReportStatus.PENDING, persisted.getStatus());
        assertNotNull(persisted.getCreatedAt());
        assertNotNull(persisted.getDateFrom());
        assertNotNull(persisted.getDateTo());
        assertTrue(persisted.getDateFrom().before(persisted.getDateTo()));
        assertEquals(42L, saved.getId());
    }

    @Test
    public void createReportSerializesParameters() {
        when(reportRepository.save(any(Report.class))).thenAnswer(inv -> {
            Report r = inv.getArgument(0);
            r.setId(1L);
            return r;
        });

        ReportRequest request = buildRequest();
        Map<String, String> params = new HashMap<>();
        params.put("filter", "active");
        request.setParameters(params);

        reportService.createReport(request);

        ArgumentCaptor<Report> captor = ArgumentCaptor.forClass(Report.class);
        verify(reportRepository).save(captor.capture());
        assertTrue(captor.getValue().getParameters().contains("\"filter\":\"active\""));
    }

    @Test
    public void createReportDefersAsyncGenerationUntilAfterCommit() {
        when(reportRepository.save(any(Report.class))).thenAnswer(inv -> {
            Report r = inv.getArgument(0);
            r.setId(7L);
            return r;
        });

        reportService.createReport(buildRequest());

        // Worker must NOT be invoked before the transaction commits
        verify(generationWorker, never()).generateReportAsync(any());

        List<TransactionSynchronization> synchronizations =
                TransactionSynchronizationManager.getSynchronizations();
        assertEquals(1, synchronizations.size());
        synchronizations.get(0).afterCommit();

        verify(generationWorker).generateReportAsync(7L);
    }

    @Test
    public void getReportDelegatesToRepository() {
        Report report = new Report();
        report.setId(5L);
        when(reportRepository.findById(5L)).thenReturn(Optional.of(report));

        Optional<Report> result = reportService.getReport(5L);

        assertTrue(result.isPresent());
        assertEquals(5L, result.get().getId());
    }

    @Test
    public void getReportsByUserDelegatesToRepository() {
        when(reportRepository.findByRequestedByOrderByCreatedAtDesc("user-1"))
                .thenReturn(Arrays.asList(new Report(), new Report()));

        assertEquals(2, reportService.getReportsByUser("user-1").size());
    }

    @Test
    public void getReportsByStatusDelegatesToRepository() {
        when(reportRepository.findByStatusOrderByCreatedAtAsc(ReportStatus.COMPLETED))
                .thenReturn(Collections.singletonList(new Report()));

        assertEquals(1, reportService.getReportsByStatus(ReportStatus.COMPLETED).size());
    }

    @Test
    public void deleteReportReturnsFalseWhenReportMissing() {
        when(reportRepository.findById(99L)).thenReturn(Optional.empty());

        assertFalse(reportService.deleteReport(99L));
        verify(reportRepository, never()).deleteById(any());
    }

    @Test
    public void deleteReportRemovesRecordAndReturnsTrue() {
        Report report = new Report();
        report.setId(3L);
        when(reportRepository.findById(3L)).thenReturn(Optional.of(report));

        assertTrue(reportService.deleteReport(3L));
        verify(reportRepository).deleteById(3L);
    }
}
