package com.otterworks.report.service;

import com.otterworks.report.model.Report;
import com.otterworks.report.model.ReportCategory;
import com.otterworks.report.model.ReportStatus;
import com.otterworks.report.model.ReportType;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

/**
 * Unit tests for {@link ExcelReportGenerator}.
 *
 * Uses Apache POI to read back the generated .xlsx file and verify its
 * structure: sheet names, summary metadata, column headers, and data rows.
 * Does not require a Spring context.
 *
 * Written in JUnit 4 style to match the current stack. After the JUnit 5
 * migration (Axis 4), replace:
 *   - org.junit.Test   -> org.junit.jupiter.api.Test
 *   - org.junit.Before -> org.junit.jupiter.api.BeforeEach
 *   - org.junit.After  -> org.junit.jupiter.api.AfterEach
 *   - org.junit.Assert -> org.junit.jupiter.api.Assertions
 */
public class ExcelReportGeneratorTest {

    private ExcelReportGenerator generator;
    private File outputDir;

    @Before
    public void setUp() {
        generator = new ExcelReportGenerator();
        outputDir = new File(System.getProperty("java.io.tmpdir"), "excel-test-" + System.currentTimeMillis());
        outputDir.mkdirs();
    }

    @After
    public void tearDown() {
        if (outputDir != null && outputDir.exists()) {
            File[] files = outputDir.listFiles();
            if (files != null) {
                for (File f : files) {
                    f.delete();
                }
            }
            outputDir.delete();
        }
    }

    @Test
    public void generateExcelProducesNonEmptyFile() throws IOException {
        Report report = buildReport("Storage Summary Report");
        List<Map<String, Object>> data = buildSampleData(5);

        File xlsx = generator.generateExcel(report, data, outputDir.getAbsolutePath());

        assertNotNull("Excel file should not be null", xlsx);
        assertTrue("Excel file should exist", xlsx.exists());
        assertTrue("Excel file should have content", xlsx.length() > 0);
        assertTrue("Excel file should have .xlsx extension", xlsx.getName().endsWith(".xlsx"));
    }

    @Test
    public void generatedExcelIsReadableByPoi() throws IOException {
        Report report = buildReport("Readable Excel Report");
        List<Map<String, Object>> data = buildSampleData(3);

        File xlsx = generator.generateExcel(report, data, outputDir.getAbsolutePath());

        try (FileInputStream fis = new FileInputStream(xlsx);
             Workbook workbook = new XSSFWorkbook(fis)) {
            assertNotNull("Workbook should not be null", workbook);
            assertTrue("Workbook should have at least one sheet",
                    workbook.getNumberOfSheets() > 0);
        }
    }

    @Test
    public void generatedExcelHasSummaryAndDataSheets() throws IOException {
        Report report = buildReport("Two Sheet Report");
        List<Map<String, Object>> data = buildSampleData(5);

        File xlsx = generator.generateExcel(report, data, outputDir.getAbsolutePath());

        try (FileInputStream fis = new FileInputStream(xlsx);
             Workbook workbook = new XSSFWorkbook(fis)) {
            assertEquals("Workbook should have 2 sheets", 2, workbook.getNumberOfSheets());
            assertEquals("First sheet should be 'Summary'",
                    "Summary", workbook.getSheetName(0));
            assertEquals("Second sheet should be 'Data'",
                    "Data", workbook.getSheetName(1));
        }
    }

    @Test
    public void summarySheetContainsReportMetadata() throws IOException {
        Report report = buildReport("Metadata Verification Report");
        List<Map<String, Object>> data = buildSampleData(7);

        File xlsx = generator.generateExcel(report, data, outputDir.getAbsolutePath());

        try (FileInputStream fis = new FileInputStream(xlsx);
             Workbook workbook = new XSSFWorkbook(fis)) {
            Sheet summary = workbook.getSheet("Summary");
            assertNotNull("Summary sheet should exist", summary);

            // Row 0: Title "OtterWorks Report"
            Row titleRow = summary.getRow(0);
            assertNotNull("Title row should exist", titleRow);
            assertEquals("Title should be 'OtterWorks Report'",
                    "OtterWorks Report", titleRow.getCell(0).getStringCellValue());

            // Row 2: Report Name label and value
            Row nameRow = summary.getRow(2);
            assertNotNull("Name row should exist", nameRow);
            assertEquals("Name label", "Report Name:", nameRow.getCell(0).getStringCellValue());
            assertEquals("Name value", "Metadata Verification Report",
                    nameRow.getCell(1).getStringCellValue());

            // Row 3: Category
            Row catRow = summary.getRow(3);
            assertNotNull("Category row should exist", catRow);
            assertEquals("Category label", "Category:", catRow.getCell(0).getStringCellValue());
            assertEquals("Category value", "STORAGE_SUMMARY",
                    catRow.getCell(1).getStringCellValue());

            // Row 6: Total Rows
            Row countRow = summary.getRow(6);
            assertNotNull("Count row should exist", countRow);
            assertEquals("Count label", "Total Rows:", countRow.getCell(0).getStringCellValue());
            assertEquals("Row count should match data size",
                    7.0, countRow.getCell(1).getNumericCellValue(), 0.001);
        }
    }

    @Test
    public void dataSheetContainsCorrectHeaders() throws IOException {
        Report report = buildReport("Header Check Report");
        List<Map<String, Object>> data = buildSampleData(2);

        File xlsx = generator.generateExcel(report, data, outputDir.getAbsolutePath());

        try (FileInputStream fis = new FileInputStream(xlsx);
             Workbook workbook = new XSSFWorkbook(fis)) {
            Sheet dataSheet = workbook.getSheet("Data");
            assertNotNull("Data sheet should exist", dataSheet);

            Row headerRow = dataSheet.getRow(0);
            assertNotNull("Header row should exist", headerRow);

            // Column names are formatted by ExcelReportGenerator.formatColumnName
            // which replaces underscores with spaces and capitalizes
            List<String> expectedHeaders = new ArrayList<String>();
            expectedHeaders.add("File id");
            expectedHeaders.add("File name");
            expectedHeaders.add("Size bytes");
            expectedHeaders.add("Owner");
            expectedHeaders.add("Created at");

            for (int i = 0; i < expectedHeaders.size(); i++) {
                assertEquals("Column " + i + " header",
                        expectedHeaders.get(i),
                        headerRow.getCell(i).getStringCellValue());
            }
        }
    }

    @Test
    public void dataSheetContainsCorrectNumberOfRows() throws IOException {
        int expectedRows = 12;
        Report report = buildReport("Row Count Report");
        List<Map<String, Object>> data = buildSampleData(expectedRows);

        File xlsx = generator.generateExcel(report, data, outputDir.getAbsolutePath());

        try (FileInputStream fis = new FileInputStream(xlsx);
             Workbook workbook = new XSSFWorkbook(fis)) {
            Sheet dataSheet = workbook.getSheet("Data");
            assertNotNull("Data sheet should exist", dataSheet);

            // Physical rows = 1 header + N data rows
            assertEquals("Data sheet should have header + data rows",
                    expectedRows + 1, dataSheet.getPhysicalNumberOfRows());
        }
    }

    @Test
    public void dataSheetCellsContainExpectedValues() throws IOException {
        Report report = buildReport("Cell Value Report");
        List<Map<String, Object>> data = buildSampleData(3);

        File xlsx = generator.generateExcel(report, data, outputDir.getAbsolutePath());

        try (FileInputStream fis = new FileInputStream(xlsx);
             Workbook workbook = new XSSFWorkbook(fis)) {
            Sheet dataSheet = workbook.getSheet("Data");

            // Row 1 (first data row) should have the first record's values
            Row firstDataRow = dataSheet.getRow(1);
            assertNotNull("First data row should exist", firstDataRow);

            // file_id column (index 0) should be "file-0"
            assertEquals("First data row, file_id", "file-0",
                    firstDataRow.getCell(0).getStringCellValue());
            // file_name column (index 1) should be "document_0.pdf"
            assertEquals("First data row, file_name", "document_0.pdf",
                    firstDataRow.getCell(1).getStringCellValue());
        }
    }

    @Test
    public void generateExcelWithEmptyDataProducesValidFile() throws IOException {
        Report report = buildReport("Empty Excel Report");
        List<Map<String, Object>> emptyData = new ArrayList<Map<String, Object>>();

        File xlsx = generator.generateExcel(report, emptyData, outputDir.getAbsolutePath());

        assertNotNull("Excel file should not be null", xlsx);
        assertTrue("Excel file should exist", xlsx.exists());

        try (FileInputStream fis = new FileInputStream(xlsx);
             Workbook workbook = new XSSFWorkbook(fis)) {
            assertNotNull("Workbook should be readable", workbook);
            Sheet summary = workbook.getSheet("Summary");
            assertNotNull("Summary sheet should exist even with no data", summary);
        }
    }

    @Test
    public void generatedExcelFileNameContainsReportName() throws IOException {
        Report report = buildReport("Weekly File Usage Stats");
        List<Map<String, Object>> data = buildSampleData(1);

        File xlsx = generator.generateExcel(report, data, outputDir.getAbsolutePath());

        assertTrue("File name should contain sanitized report name",
                xlsx.getName().startsWith("weekly_file_usage_stats_"));
    }

    // ---- Helpers ----

    private Report buildReport(String name) {
        Report report = new Report();
        report.setId(1L);
        report.setReportName(name);
        report.setCategory(ReportCategory.STORAGE_SUMMARY);
        report.setReportType(ReportType.EXCEL);
        report.setStatus(ReportStatus.GENERATING);
        report.setRequestedBy("test-user");
        report.setDateFrom(new Date(System.currentTimeMillis() - 86400000L * 30));
        report.setDateTo(new Date());
        report.setCreatedAt(new Date());
        return report;
    }

    private List<Map<String, Object>> buildSampleData(int rows) {
        List<Map<String, Object>> data = new ArrayList<Map<String, Object>>();
        String[] extensions = {"pdf", "docx", "xlsx", "png", "txt"};
        String[] owners = {"alice", "bob", "carol", "dave", "eve"};

        for (int i = 0; i < rows; i++) {
            Map<String, Object> row = new LinkedHashMap<String, Object>();
            row.put("file_id", "file-" + i);
            row.put("file_name", "document_" + i + "." + extensions[i % extensions.length]);
            row.put("size_bytes", (i + 1) * 2048L);
            row.put("owner", owners[i % owners.length]);
            row.put("created_at", new Date(System.currentTimeMillis() - (long) i * 86400000));
            data.add(row);
        }
        return data;
    }
}
