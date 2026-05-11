using System.Text;
using FluentAssertions;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Services;

namespace ReportService.Tests.Services;

public class CsvReportGeneratorTests : IDisposable
{
    private readonly CsvReportGenerator _generator;
    private readonly string _outputDir;

    public CsvReportGeneratorTests()
    {
        var logger = new Mock<ILogger<CsvReportGenerator>>();
        _generator = new CsvReportGenerator(logger.Object);
        _outputDir = Path.Combine(Path.GetTempPath(), "test-csv-" + Guid.NewGuid());
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
        ReportName = "Test CSV Report",
        Category = ReportCategory.AUDIT_LOG,
        ReportType = ReportType.CSV,
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
                ["audit_id"] = $"aud-{i:D4}",
                ["action"] = "LOGIN",
                ["actor"] = $"user-{i:D3}",
                ["result"] = "SUCCESS"
            });
        }
        return data;
    }

    [Fact]
    public void GenerateCsv_ShouldCreateFileWithHeaderRow()
    {
        var report = CreateTestReport();
        var data = CreateTestData();

        var path = _generator.GenerateCsv(report, data, _outputDir);

        File.Exists(path).Should().BeTrue();
        var content = File.ReadAllText(path);
        content.Should().Contain("audit_id");
        content.Should().Contain("action");
        content.Should().Contain("actor");
        content.Should().Contain("result");
    }

    [Fact]
    public void GenerateCsv_ShouldContainMetadataComments()
    {
        var report = CreateTestReport();
        var data = CreateTestData();

        var path = _generator.GenerateCsv(report, data, _outputDir);

        var content = File.ReadAllText(path);
        content.Should().Contain("# OtterWorks Report: Test CSV Report");
        content.Should().Contain("# Generated:");
        content.Should().Contain("# Period:");
        content.Should().Contain("# Rows: 5");
    }

    [Fact]
    public void GenerateCsv_WithEmptyData_ShouldProduceEmptyFile()
    {
        var report = CreateTestReport();
        var data = new List<Dictionary<string, object>>();

        var path = _generator.GenerateCsv(report, data, _outputDir);

        File.Exists(path).Should().BeTrue();
        var content = File.ReadAllText(path);
        content.Should().NotContain("audit_id");
    }

    [Fact]
    public void GenerateCsv_ShouldBeUtf8Encoded()
    {
        var report = CreateTestReport();
        var data = CreateTestData();

        var path = _generator.GenerateCsv(report, data, _outputDir);

        var bytes = File.ReadAllBytes(path);
        // UTF-8 BOM or valid UTF-8
        var text = Encoding.UTF8.GetString(bytes);
        text.Should().Contain("audit_id");
    }
}
