using ClosedXML.Excel;
using FluentAssertions;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Services;

namespace ReportService.Tests.Services;

public class ExcelReportGeneratorTests : IDisposable
{
    private readonly ExcelReportGenerator _generator;
    private readonly string _outputDir;

    public ExcelReportGeneratorTests()
    {
        var logger = new Mock<ILogger<ExcelReportGenerator>>();
        _generator = new ExcelReportGenerator(logger.Object);
        _outputDir = Path.Combine(Path.GetTempPath(), "test-excel-" + Guid.NewGuid());
        Directory.CreateDirectory(_outputDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_outputDir))
            Directory.Delete(_outputDir, true);
    }

    private static Report CreateTestReport() => new()
    {
        Id = 1,
        ReportName = "Test Excel Report",
        Category = ReportCategory.USER_ACTIVITY,
        ReportType = ReportType.EXCEL,
        Status = ReportStatus.PENDING,
        RequestedBy = "test-user",
        CreatedAt = DateTime.UtcNow,
        DateFrom = DateTime.UtcNow.AddDays(-30),
        DateTo = DateTime.UtcNow
    };

    private static List<Dictionary<string, object>> CreateTestData(int count = 5)
    {
        var data = new List<Dictionary<string, object>>();
        for (int i = 0; i < count; i++)
        {
            data.Add(new Dictionary<string, object>
            {
                ["user_id"] = $"user-{i:D3}",
                ["email"] = $"user{i}@test.com",
                ["files_uploaded"] = 10 + i
            });
        }
        return data;
    }

    [Fact]
    public void GenerateExcel_ShouldCreateFileWithSummaryAndDataSheets()
    {
        var report = CreateTestReport();
        var data = CreateTestData();

        var path = _generator.GenerateExcel(report, data, _outputDir);

        File.Exists(path).Should().BeTrue();
        Path.GetExtension(path).Should().Be(".xlsx");

        using var workbook = new XLWorkbook(path);
        workbook.Worksheets.Count.Should().BeGreaterThanOrEqualTo(2);
        workbook.Worksheets.Any(ws => ws.Name == "Summary").Should().BeTrue();
        workbook.Worksheets.Any(ws => ws.Name == "Data").Should().BeTrue();
    }

    [Fact]
    public void GenerateExcel_SummarySheet_ShouldContainMetadata()
    {
        var report = CreateTestReport();
        var data = CreateTestData();

        var path = _generator.GenerateExcel(report, data, _outputDir);

        using var workbook = new XLWorkbook(path);
        var summary = workbook.Worksheet("Summary");
        summary.Cell(1, 1).GetString().Should().Be("OtterWorks Report");
        summary.Cell(3, 2).GetString().Should().Be("Test Excel Report");
    }

    [Fact]
    public void GenerateExcel_DataSheet_ShouldMatchInputRowCount()
    {
        var report = CreateTestReport();
        var data = CreateTestData(10);

        var path = _generator.GenerateExcel(report, data, _outputDir);

        using var workbook = new XLWorkbook(path);
        var dataSheet = workbook.Worksheet("Data");
        // 1 header row + 10 data rows
        dataSheet.RowsUsed().Count().Should().Be(11);
    }

    [Fact]
    public void GenerateExcel_WithEmptyData_ShouldProduceFileWithEmptyDataSheet()
    {
        var report = CreateTestReport();
        var data = new List<Dictionary<string, object>>();

        var path = _generator.GenerateExcel(report, data, _outputDir);

        File.Exists(path).Should().BeTrue();
        using var workbook = new XLWorkbook(path);
        var dataSheet = workbook.Worksheet("Data");
        dataSheet.RowsUsed().Count().Should().Be(0);
    }
}
