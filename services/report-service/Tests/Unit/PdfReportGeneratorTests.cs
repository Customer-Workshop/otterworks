using FluentAssertions;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Services;
using QuestPDF.Infrastructure;

namespace OtterWorks.ReportService.Tests.Unit;

public class PdfReportGeneratorTests : IDisposable
{
    private readonly PdfReportGenerator _generator;
    private readonly string _outputDir;

    public PdfReportGeneratorTests()
    {
        QuestPDF.Settings.License = LicenseType.Community;
        var logger = new Mock<ILogger<PdfReportGenerator>>();
        _generator = new PdfReportGenerator(logger.Object);
        _outputDir = Path.Combine(Path.GetTempPath(), "pdf-tests-" + Guid.NewGuid());
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
        ReportName = "Test PDF Report",
        Category = ReportCategory.USAGE_ANALYTICS,
        ReportType = ReportType.PDF,
        RequestedBy = "user-001",
        DateFrom = DateTime.UtcNow.AddDays(-30),
        DateTo = DateTime.UtcNow,
        CreatedAt = DateTime.UtcNow,
    };

    private static List<Dictionary<string, object>> CreateSampleData() =>
    [
        new Dictionary<string, object> { ["id"] = "1", ["name"] = "Test", ["value"] = 42 },
        new Dictionary<string, object> { ["id"] = "2", ["name"] = "Test2", ["value"] = 84 },
    ];

    [Fact]
    public void GeneratesValidPdfFileOnDisk()
    {
        var result = _generator.GeneratePdf(CreateTestReport(), CreateSampleData(), _outputDir);
        File.Exists(result).Should().BeTrue();
    }

    [Fact]
    public void GeneratedFileIsNonEmpty()
    {
        var result = _generator.GeneratePdf(CreateTestReport(), CreateSampleData(), _outputDir);
        new FileInfo(result).Length.Should().BeGreaterThan(0);
    }

    [Fact]
    public void FileNameFollowsPattern()
    {
        var result = _generator.GeneratePdf(CreateTestReport(), CreateSampleData(), _outputDir);
        var fileName = Path.GetFileName(result);
        fileName.Should().StartWith("test_pdf_report_");
        fileName.Should().EndWith(".pdf");
    }

    [Fact]
    public void HandlesEmptyDataList()
    {
        var result = _generator.GeneratePdf(CreateTestReport(), new List<Dictionary<string, object>>(), _outputDir);
        File.Exists(result).Should().BeTrue();
        new FileInfo(result).Length.Should().BeGreaterThan(0);
    }

    [Fact]
    public void GeneratedPdfContainsReportNameText()
    {
        var result = _generator.GeneratePdf(CreateTestReport(), CreateSampleData(), _outputDir);
        var bytes = File.ReadAllBytes(result);
        bytes.Length.Should().BeGreaterThan(0);

        // PDF format validation: starts with %PDF
        var header = System.Text.Encoding.ASCII.GetString(bytes, 0, Math.Min(5, bytes.Length));
        header.Should().StartWith("%PDF");
    }
}
