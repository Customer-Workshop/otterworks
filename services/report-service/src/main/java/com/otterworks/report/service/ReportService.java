package com.otterworks.report.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.otterworks.report.config.AppConfig;
import com.otterworks.report.model.Report;
import com.otterworks.report.model.ReportCategory;
import com.otterworks.report.model.ReportRequest;
import com.otterworks.report.model.ReportStatus;
import com.otterworks.report.model.ReportType;
import com.otterworks.report.repository.ReportRepository;
import com.otterworks.report.util.DateUtils2;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import javax.transaction.Transactional;
import java.io.File;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Core report orchestration service.
 *
 * LEGACY PATTERNS:
 * - javax.transaction.Transactional (target: jakarta.transaction.Transactional
 *   or org.springframework.transaction.annotation.Transactional)
 * - java.util.Date throughout
 * - @Async without CompletableFuture return (fire-and-forget, no error propagation)
 * - Manual JSON serialization for parameters
 * - Checked exceptions caught and rethrown as generic RuntimeException
 */
@Service
public class ReportService {

    private static final Logger logger = LoggerFactory.getLogger(ReportService.class);

    private final ReportRepository reportRepository;
    private final ReportDataFetcher dataFetcher;
    private final PdfReportGenerator pdfGenerator;
    private final CsvReportGenerator csvGenerator;
    private final ExcelReportGenerator excelGenerator;
    private final AppConfig appConfig;
    private final ObjectMapper objectMapper;

    public ReportService(
            ReportRepository reportRepository,
            ReportDataFetcher dataFetcher,
            PdfReportGenerator pdfGenerator,
            CsvReportGenerator csvGenerator,
            ExcelReportGenerator excelGenerator,
            AppConfig appConfig) {
        this.reportRepository = reportRepository;
        this.dataFetcher = dataFetcher;
        this.pdfGenerator = pdfGenerator;
        this.csvGenerator = csvGenerator;
        this.excelGenerator = excelGenerator;
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
        report.setDateFrom(request.getDateFrom() != null ? request.getDateFrom() : DateUtils2.daysAgo(30));
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

        // Kick off async generation
        generateReportAsync(saved.getId());

        return saved;
    }

    /**
     * Async report generation — runs in background thread pool.
     *
     * LEGACY: @Async with no return type (fire-and-forget).
     * Modern approach: return CompletableFuture<Void> or use reactive pipeline.
     */
    @Async
    public void generateReportAsync(Long reportId) {
        Optional<Report> optReport = reportRepository.findById(reportId);
        if (!optReport.isPresent()) { // LEGACY: !isPresent() instead of isEmpty() (Java 11+)
            logger.error("Report not found for generation: {}", reportId);
            return;
        }

        Report report = optReport.get();
        report.setStatus(ReportStatus.GENERATING);
        reportRepository.save(report);

        try {
            // Parse parameters
            Map<String, String> params = null;
            if (report.getParameters() != null) {
                params = objectMapper.readValue(report.getParameters(), Map.class);
            }

            // Fetch data based on category
            List<Map<String, Object>> data = fetchDataForCategory(
                    report.getCategory(), report.getDateFrom(), report.getDateTo(), params);

            // Cap at max rows
            if (data.size() > appConfig.getMaxRows()) {
                data = data.subList(0, appConfig.getMaxRows());
                logger.warn("Report {} truncated to {} rows", reportId, appConfig.getMaxRows());
            }

            // Generate report file
            File outputFile = generateFile(report, data);

            // Update report record
            report.setStatus(ReportStatus.COMPLETED);
            report.setCompletedAt(new Date());
            report.setFilePath(outputFile.getAbsolutePath());
            report.setFileSizeBytes(outputFile.length());
            report.setRowCount(data.size());
            reportRepository.save(report);

            String duration = DateUtils2.humanReadableDuration(report.getCreatedAt(), report.getCompletedAt());
            logger.info("Report {} completed: {} rows, {} bytes, took {}",
                    reportId, data.size(), outputFile.length(), duration);

        } catch (Exception e) {
            logger.error("Report generation failed for {}: {}", reportId, e.getMessage(), e);
            report.setStatus(ReportStatus.FAILED);
            report.setCompletedAt(new Date());
            report.setErrorMessage(e.getMessage());
            reportRepository.save(report);
        }
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

    // ----- Private helpers -----

    private List<Map<String, Object>> fetchDataForCategory(
            ReportCategory category, Date dateFrom, Date dateTo, Map<String, String> params) {

        // LEGACY: switch with fall-through instead of enhanced switch (Java 14+)
        switch (category) {
            case USAGE_ANALYTICS:
            case COLLABORATION_METRICS:
            case SYSTEM_HEALTH:
                return dataFetcher.fetchAnalyticsData(dateFrom, dateTo, params);
            case AUDIT_LOG:
            case COMPLIANCE:
                return dataFetcher.fetchAuditData(dateFrom, dateTo, params);
            case USER_ACTIVITY:
            case STORAGE_SUMMARY:
                return dataFetcher.fetchUserActivityData(dateFrom, dateTo, params);
            default:
                logger.warn("Unknown category: {}, defaulting to analytics", category);
                return dataFetcher.fetchAnalyticsData(dateFrom, dateTo, params);
        }
    }

    private File generateFile(Report report, List<Map<String, Object>> data) throws Exception {
        String outputDir = appConfig.getReportOutputDir();

        // LEGACY: switch without enhanced syntax
        switch (report.getReportType()) {
            case PDF:
                return pdfGenerator.generatePdf(report, data, outputDir);
            case CSV:
                return csvGenerator.generateCsv(report, data, outputDir);
            case EXCEL:
                return excelGenerator.generateExcel(report, data, outputDir);
            default:
                throw new IllegalArgumentException("Unsupported report type: " + report.getReportType());
        }
    }
}
