package com.otterworks.report.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.otterworks.report.config.AppConfig;
import com.otterworks.report.model.Report;
import com.otterworks.report.model.ReportRequest;
import com.otterworks.report.model.ReportStatus;
import com.otterworks.report.repository.ReportRepository;
import com.otterworks.report.util.ReportDateUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

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
    public Report createReport(ReportRequest request) {
        Report report = new Report();
        report.setReportName(request.getReportName());
        report.setCategory(request.getCategory());
        report.setReportType(request.getReportType());
        report.setRequestedBy(request.getRequestedBy());
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

        // Kick off async generation via separate bean (avoids self-invocation proxy bypass)
        generationWorker.generateReportAsync(saved.getId());

        return saved;
    }

    /**
     * Get a report by ID.
     */
    public Optional<Report> getReport(Long id) {
        return reportRepository.findById(id);
    }

    /**
     * List all reports for a user.
     */
    public List<Report> getReportsByUser(String userId) {
        return reportRepository.findByRequestedByOrderByCreatedAtDesc(userId);
    }

    /**
     * List reports by status.
     */
    public List<Report> getReportsByStatus(ReportStatus status) {
        return reportRepository.findByStatusOrderByCreatedAtAsc(status);
    }

    /**
     * Delete a report and its generated file.
     */
    @Transactional
    public boolean deleteReport(Long id) {
        Optional<Report> optReport = reportRepository.findById(id);
        if (!optReport.isPresent()) {
            return false;
        }

        Report report = optReport.get();

        // Delete file if exists
        if (report.getFilePath() != null) {
            File file = new File(report.getFilePath());
            if (file.exists()) {
                boolean deleted = file.delete();
                if (!deleted) {
                    logger.warn("Failed to delete report file: {}", report.getFilePath());
                }
            }
        }

        reportRepository.deleteById(id);
        logger.info("Deleted report: {}", id);
        return true;
    }

}
