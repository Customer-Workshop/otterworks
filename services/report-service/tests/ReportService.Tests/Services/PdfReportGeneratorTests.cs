using FluentAssertions;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Services;

namespace ReportService.Tests.Services;

public class PdfReportGeneratorTests : IDisposable
{
    private readonly PdfReportGenerator _generator;
    private readonly string _outputDir;

    public PdfReportGeneratorTests()
    {
        var logger = new Mock<ILogger<PdfReportGenerator>>();
        _generator = new PdfReportGenerator(logger.Object);
        _outputDir = Path.Combine(Path.GetTempPath(), "test-pdf-" + Guid.NewGuid());
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
        ReportName = "Test PDF Report",
        Category = ReportCategory.USAGE_ANALYTICS,
        ReportType = ReportType.PDF,
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
                ["event_id"] = $"evt-{i:D4}",
                ["event_type"] = "file_upload",
                ["user_id"] = $"user-{i:D3}",
                ["status"] = "success"
            });
        }
        return data;
    }

    [Fact]
    public void GeneratePdf_ShouldCreateValidFile()
    {
        var report = CreateTestReport();
        var data = CreateTestData();

        var path = _generator.GeneratePdf(report, data, _outputDir);

        File.Exists(path).Should().BeTrue();
        new FileInfo(path).Length.Should().BeGreaterThan(0);
        Path.GetExtension(path).Should().Be(".pdf");
    }

    [Fact]
    public void GeneratePdf_ShouldContainPdfHeader()
    {
        var report = CreateTestReport();
        var data = CreateTestData();

        var path = _generator.GeneratePdf(report, data, _outputDir);

        var bytes = File.ReadAllBytes(path);
        var header = System.Text.Encoding.ASCII.GetString(bytes, 0, Math.Min(5, bytes.Length));
        header.Should().Be("%PDF-");
    }

    [Fact]
    public void GeneratePdf_WithEmptyData_ShouldProduceValidFile()
    {
        var report = CreateTestReport();
        var data = new List<Dictionary<string, object>>();

        var path = _generator.GeneratePdf(report, data, _outputDir);

        File.Exists(path).Should().BeTrue();
        new FileInfo(path).Length.Should().BeGreaterThan(0);
    }

    [Fact]
    public void GeneratePdf_ShouldWriteToSpecifiedDirectory()
    {
        var report = CreateTestReport();
        var data = CreateTestData();

        var path = _generator.GeneratePdf(report, data, _outputDir);

        Path.GetDirectoryName(path).Should().Be(_outputDir);
    }
}
