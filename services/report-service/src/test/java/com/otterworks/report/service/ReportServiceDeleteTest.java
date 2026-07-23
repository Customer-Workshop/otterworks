package com.otterworks.report.service;

import com.otterworks.report.model.Report;
import com.otterworks.report.model.ReportCategory;
import com.otterworks.report.model.ReportStatus;
import com.otterworks.report.model.ReportType;
import com.otterworks.report.repository.ReportRepository;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit4.SpringRunner;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.util.Date;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

/**
 * Tests for {@link ReportService#deleteReport(Long)}.
 *
 * Verifies the record is removed and that the generated file is deleted
 * after the transaction commits (deferred deletion).
 */
@RunWith(SpringRunner.class)
@SpringBootTest
@ActiveProfiles("test")
public class ReportServiceDeleteTest {

    @Autowired
    private ReportService reportService;

    @Autowired
    private ReportRepository reportRepository;

    private Report persistReport(String filePath) {
        Report report = new Report();
        report.setReportName("Delete Test Report");
        report.setCategory(ReportCategory.AUDIT_LOG);
        report.setReportType(ReportType.CSV);
        report.setStatus(ReportStatus.COMPLETED);
        report.setRequestedBy("delete-test-user");
        report.setCreatedAt(new Date());
        report.setFilePath(filePath);
        return reportRepository.save(report);
    }

    private File createTempReportFile() throws IOException {
        File file = File.createTempFile("report-delete-test", ".csv");
        try (FileWriter writer = new FileWriter(file)) {
            writer.write("col1,col2\nval1,val2\n");
        }
        return file;
    }

    @Test
    public void deleteReportRemovesRecordAndFileAfterCommit() throws IOException {
        File file = createTempReportFile();
        Report saved = persistReport(file.getAbsolutePath());

        boolean deleted = reportService.deleteReport(saved.getId());

        assertTrue("deleteReport should return true", deleted);
        assertFalse("Report record should be removed",
                reportRepository.findById(saved.getId()).isPresent());
        assertFalse("Generated file should be deleted after commit", file.exists());
    }

    @Test
    public void deleteReportWithoutFilePathRemovesRecord() {
        Report saved = persistReport(null);

        boolean deleted = reportService.deleteReport(saved.getId());

        assertTrue("deleteReport should return true", deleted);
        assertFalse("Report record should be removed",
                reportRepository.findById(saved.getId()).isPresent());
    }

    @Test
    public void deleteReportWithMissingFileStillSucceeds() {
        Report saved = persistReport("/tmp/reports/nonexistent-file-xyz.csv");

        boolean deleted = reportService.deleteReport(saved.getId());

        assertTrue("deleteReport should return true even if file is missing", deleted);
        assertFalse(reportRepository.findById(saved.getId()).isPresent());
    }

    @Test
    public void deleteNonExistentReportReturnsFalse() {
        assertFalse(reportService.deleteReport(987654321L));
    }
}
