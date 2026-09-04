package com.otterworks.report.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.otterworks.report.config.AppConfig;
import com.otterworks.report.model.Report;
import com.otterworks.report.model.ReportRequest;
import com.otterworks.report.model.ReportStatus;
import com.otterworks.report.repository.ReportRepository;
import com.otterworks.report.security.ReportAccessDeniedException;
import com.otterworks.report.util.ReportDateUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import javax.transaction.Transactional;
import java.io.File;
import java.util.Date;
import java.util.List;
import java.util.Optional;

/**
 * Core report orchestration service.
 *
 * LEGACY PATTERNS:
 * - javax.transaction.Transactional (target: jakarta.transaction.Transactional
 *   or org.springframework.transaction.annotation.Transactional)
 * - java.util.Date throughout
 * - @Async delegated to ReportGenerationWorker (fire-and-forget, no error propagation)
 * - Manual JSON serialization for parameters
 * - Checked exceptions caught and rethrown as generic RuntimeException
 */
@Service
public class ReportService {

    private static final Logger logger = LoggerFactory.getLogger(ReportService.class);

    private final ReportRepository reportRepository;
    private final ReportGenerationWorker generationWorker;
    private final AppConfig appConfig;
    private final ObjectMapper objectMapper;

    public ReportService(
            ReportRepository reportRepository,
            ReportGenerationWorker generationWorker,
            AppConfig appConfig) {
        this.reportRepository = reportRepository;
        this.generationWorker = generationWorker;
        this.appConfig = appConfig;
        this.objectMapper = new ObjectMapper();
    }

    /**
     * Create a new report request and start async generation.
     */
    @Transactional
    public Report createReport(ReportRequest request, String callerId) {
        Report report = new Report();
        report.setReportName(request.getReportName());
        report.setCategory(request.getCategory());
        report.setReportType(request.getReportType());
        report.setRequestedBy(callerId);
        report.setStatus(ReportStatus.PENDING);
        report.setCreatedAt(new Date()); // LEGACY: new Date() instead of Instant.now()

        // Default date range: last 30 days
        report.setDateFrom(request.getDateFrom() != null ? request.getDateFrom() : ReportDateUtils.daysAgo(30));
        report.setDateTo(request.getDateTo() != null ? request.getDateTo() : new Date());

        // Serialize parameters
        if (request.getParameters() != null) {
            try {
                report.setParameters(objectMapper.writeValueAsString(request.getParameters()));
            } catch (JsonProcessingException e) {
                logger.warn("Failed to serialize report parameters: {}", e.getMessage());
            }
        }

        Report saved = reportRepository.save(report);
        logger.info("Created report request: id={}, name={}, type={}",
                saved.getId(), saved.getReportName(), saved.getReportType());

        // Defer async generation until after @Transactional commit so the worker thread
        // can see the persisted report (avoids race where findById returns empty).
        // LEGACY: TransactionSynchronization callback — modern approach uses @TransactionalEventListener.
        final Long reportId = saved.getId();
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                generationWorker.generateReportAsync(reportId);
            }
        });

        return saved;
    }

    /**
     * Get a report by ID on behalf of a caller.
     *
     * @throws ReportAccessDeniedException if the report belongs to another user
     */
    public Optional<Report> getReport(Long id, String callerId) {
        Optional<Report> report = reportRepository.findById(id);
        if (report.isPresent()) {
            requireOwner(report.get(), callerId);
        }
        return report;
    }

    /**
     * List the caller's reports, optionally filtered by status.
     */
    public List<Report> getReports(String callerId, ReportStatus status) {
        if (status != null) {
            return reportRepository.findByRequestedByAndStatusOrderByCreatedAtDesc(callerId, status);
        }
        return reportRepository.findByRequestedByOrderByCreatedAtDesc(callerId);
    }

    /**
     * Delete a report and its generated file.
     * File deletion is deferred to afterCommit to avoid inconsistency on rollback.
     */
    @Transactional
    public boolean deleteReport(Long id, String callerId) {
        Optional<Report> optReport = reportRepository.findById(id);
        if (!optReport.isPresent()) {
            return false;
        }

        Report report = optReport.get();
        requireOwner(report, callerId);
        final String filePath = report.getFilePath();

        // Delete DB record first
        reportRepository.deleteById(id);
        logger.info("Deleted report: {}", id);

        // Defer file deletion until after transaction commits so a rollback
        // doesn't leave the DB record pointing to a missing file.
        if (filePath != null) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    File file = new File(filePath);
                    if (file.exists()) {
                        boolean deleted = file.delete();
                        if (!deleted) {
                            logger.warn("Failed to delete report file: {}", filePath);
                        }
                    }
                }
            });
        }

        return true;
    }

    /**
     * Single ownership rule for the service: a report is only accessible to the
     * user it was requested by. There is no share or role model for reports.
     */
    private void requireOwner(Report report, String callerId) {
        if (!callerId.equals(report.getRequestedBy())) {
            logger.warn("Ownership check failed for report {} (caller={})", report.getId(), callerId);
            throw new ReportAccessDeniedException(report.getId(), callerId);
        }
    }

}
