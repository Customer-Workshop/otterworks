using FluentAssertions;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Services;

namespace OtterWorks.ReportService.Tests.Unit;

public class CsvReportGeneratorTests : IDisposable
{
    private readonly CsvReportGenerator _generator;
    private readonly string _outputDir;

    public CsvReportGeneratorTests()
    {
        var logger = new Mock<ILogger<CsvReportGenerator>>();
        _generator = new CsvReportGenerator(logger.Object);
        _outputDir = Path.Combine(Path.GetTempPath(), "csv-tests-" + Guid.NewGuid());
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
        ReportName = "Test CSV Report",
        Category = ReportCategory.AUDIT_LOG,
        ReportType = ReportType.CSV,
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
    public void GeneratesValidCsvFileOnDisk()
    {
        var result = _generator.GenerateCsv(CreateTestReport(), CreateSampleData(), _outputDir);
        File.Exists(result).Should().BeTrue();
    }

    [Fact]
    public void CsvContainsMetadataCommentRows()
    {
        var result = _generator.GenerateCsv(CreateTestReport(), CreateSampleData(), _outputDir);
        var content = File.ReadAllText(result);
        content.Should().Contain("# OtterWorks Report: Test CSV Report");
        content.Should().Contain("# Generated:");
        content.Should().Contain("# Period:");
        content.Should().Contain("# Rows: 3");
    }

    [Fact]
    public void CsvContainsHeaderRowMatchingDataKeys()
    {
        var result = _generator.GenerateCsv(CreateTestReport(), CreateSampleData(), _outputDir);
        var lines = File.ReadAllLines(result);
        var headerLine = lines.First(l => !l.StartsWith("#") && !string.IsNullOrWhiteSpace(l));
        headerLine.Should().Contain("id");
        headerLine.Should().Contain("name");
        headerLine.Should().Contain("value");
    }

    [Fact]
    public void CsvContainsCorrectNumberOfDataRows()
    {
        var result = _generator.GenerateCsv(CreateTestReport(), CreateSampleData(), _outputDir);
        var lines = File.ReadAllLines(result);
        var dataLines = lines.Where(l => !l.StartsWith("#") && !string.IsNullOrWhiteSpace(l)).ToList();
        // 1 header + 3 data rows = 4
        dataLines.Should().HaveCount(4);
    }

    [Fact]
    public void FileIsUtf8Encoded()
    {
        var result = _generator.GenerateCsv(CreateTestReport(), CreateSampleData(), _outputDir);
        var bytes = File.ReadAllBytes(result);
        // UTF-8 BOM: EF BB BF
        bytes[0].Should().Be(0xEF);
        bytes[1].Should().Be(0xBB);
        bytes[2].Should().Be(0xBF);
    }

    [Fact]
    public void HandlesEmptyDataList()
    {
        var result = _generator.GenerateCsv(CreateTestReport(), new List<Dictionary<string, object>>(), _outputDir);
        File.Exists(result).Should().BeTrue();
    }
}
