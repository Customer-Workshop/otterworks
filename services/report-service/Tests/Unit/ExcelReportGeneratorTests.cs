using ClosedXML.Excel;
using FluentAssertions;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Services;

namespace OtterWorks.ReportService.Tests.Unit;

public class ExcelReportGeneratorTests : IDisposable
{
    private readonly ExcelReportGenerator _generator;
    private readonly string _outputDir;

    public ExcelReportGeneratorTests()
    {
        var logger = new Mock<ILogger<ExcelReportGenerator>>();
        _generator = new ExcelReportGenerator(logger.Object);
        _outputDir = Path.Combine(Path.GetTempPath(), "excel-tests-" + Guid.NewGuid());
        Directory.CreateDirectory(_outputDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_outputDir))
        {
            Directory.Delete(_outputDir, true);
        }
    }

    private static Report CreateTestReport() => new()
    {
        Id = 1,
        ReportName = "Test Excel Report",
        Category = ReportCategory.USER_ACTIVITY,
        ReportType = ReportType.EXCEL,
        RequestedBy = "user-001",
        DateFrom = DateTime.UtcNow.AddDays(-30),
        DateTo = DateTime.UtcNow,
        CreatedAt = DateTime.UtcNow,
    };

    private static List<Dictionary<string, object>> CreateSampleData() =>
    [
        new Dictionary<string, object> { ["id"] = "1", ["name"] = "Test", ["value"] = "42" },
        new Dictionary<string, object> { ["id"] = "2", ["name"] = "Test2", ["value"] = "84" },
        new Dictionary<string, object> { ["id"] = "3", ["name"] = "Test3", ["value"] = "126" },
    ];

    [Fact]
    public void GeneratesValidXlsxFileOnDisk()
    {
        var result = _generator.GenerateExcel(CreateTestReport(), CreateSampleData(), _outputDir);
        File.Exists(result).Should().BeTrue();
        result.Should().EndWith(".xlsx");
    }

    [Fact]
    public void ExcelHasSummaryAndDataSheets()
    {
        var result = _generator.GenerateExcel(CreateTestReport(), CreateSampleData(), _outputDir);
        using var workbook = new XLWorkbook(result);
        workbook.Worksheets.Count.Should().Be(2);
        workbook.Worksheets.Any(ws => ws.Name == "Summary").Should().BeTrue();
        workbook.Worksheets.Any(ws => ws.Name == "Data").Should().BeTrue();
    }

    [Fact]
    public void SummarySheetContainsReportMetadata()
    {
        var result = _generator.GenerateExcel(CreateTestReport(), CreateSampleData(), _outputDir);
        using var workbook = new XLWorkbook(result);
        var summary = workbook.Worksheet("Summary");
        summary.Cell(1, 1).GetString().Should().Contain("OtterWorks Report");
        summary.Cell(3, 1).GetString().Should().Contain("Report Name");
        summary.Cell(3, 2).GetString().Should().Contain("Test Excel Report");
        summary.Cell(4, 1).GetString().Should().Contain("Category");
        summary.Cell(7, 1).GetString().Should().Contain("Total Rows");
        summary.Cell(8, 1).GetString().Should().Contain("Requested By");
    }

    [Fact]
    public void DataSheetHeaderRowMatchesDataKeys()
    {
        var result = _generator.GenerateExcel(CreateTestReport(), CreateSampleData(), _outputDir);
        using var workbook = new XLWorkbook(result);
        var dataSheet = workbook.Worksheet("Data");
        dataSheet.Cell(1, 1).GetString().Should().Be("Id");
        dataSheet.Cell(1, 2).GetString().Should().Be("Name");
        dataSheet.Cell(1, 3).GetString().Should().Be("Value");
    }

    [Fact]
    public void DataSheetHasCorrectNumberOfRows()
    {
        var result = _generator.GenerateExcel(CreateTestReport(), CreateSampleData(), _outputDir);
        using var workbook = new XLWorkbook(result);
        var dataSheet = workbook.Worksheet("Data");
        // 1 header + 3 data rows = last used row should be 4
        dataSheet.LastRowUsed()!.RowNumber().Should().Be(4);
    }

    [Fact]
    public void HandlesEmptyDataList()
    {
        var result = _generator.GenerateExcel(CreateTestReport(), new List<Dictionary<string, object>>(), _outputDir);
        File.Exists(result).Should().BeTrue();
        using var workbook = new XLWorkbook(result);
        workbook.Worksheets.Count.Should().Be(2);
    }
}
