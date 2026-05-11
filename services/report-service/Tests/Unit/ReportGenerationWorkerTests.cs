using System.Threading.Channels;
using FluentAssertions;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;
using OtterWorks.ReportService.Configuration;
using OtterWorks.ReportService.Data;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Services;

namespace OtterWorks.ReportService.Tests.Unit;

public class ReportGenerationWorkerTests
{
    private readonly Mock<IReportRepository> _repoMock;
    private readonly Mock<IReportDataFetcher> _fetcherMock;
    private readonly Mock<IPdfReportGenerator> _pdfMock;
    private readonly Mock<ICsvReportGenerator> _csvMock;
    private readonly Mock<IExcelReportGenerator> _excelMock;
    private readonly ReportGenerationWorker _worker;
    private readonly string _outputDir;

    public ReportGenerationWorkerTests()
    {
        _repoMock = new Mock<IReportRepository>();
        _fetcherMock = new Mock<IReportDataFetcher>();
        _pdfMock = new Mock<IPdfReportGenerator>();
        _csvMock = new Mock<ICsvReportGenerator>();
        _excelMock = new Mock<IExcelReportGenerator>();

        _outputDir = Path.Combine(Path.GetTempPath(), "test-reports-" + Guid.NewGuid());
        Directory.CreateDirectory(_outputDir);

        var services = new ServiceCollection();
        services.AddScoped(_ => _repoMock.Object);
        services.AddScoped(_ => _fetcherMock.Object);
        services.AddScoped(_ => _pdfMock.Object);
        services.AddScoped(_ => _csvMock.Object);
        services.AddScoped(_ => _excelMock.Object);
        var provider = services.BuildServiceProvider();

        var channel = Channel.CreateUnbounded<long>();
        var logger = new Mock<ILogger<ReportGenerationWorker>>();
        var settings = Options.Create(new ReportSettings
        {
            MaxRows = 50000,
            OutputDir = _outputDir,
        });

        var scopeFactory = provider.GetRequiredService<IServiceScopeFactory>();
        _worker = new ReportGenerationWorker(channel, scopeFactory, logger.Object, settings);
    }

    private static Report CreateTestReport(long id, ReportCategory category, ReportType type)
    {
        return new Report
        {
            Id = id,
            ReportName = "Test Report",
            Category = category,
            ReportType = type,
            Status = ReportStatus.PENDING,
            RequestedBy = "user-001",
            DateFrom = DateTime.UtcNow.AddDays(-30),
            DateTo = DateTime.UtcNow,
            CreatedAt = DateTime.UtcNow,
        };
    }

    private static List<Dictionary<string, object>> CreateSampleData(int count = 10)
    {
        var data = new List<Dictionary<string, object>>();
        for (int i = 0; i < count; i++)
        {
            data.Add(new Dictionary<string, object> { ["id"] = i, ["value"] = $"test-{i}" });
        }

        return data;
    }

    [Fact]
    public async Task GeneratesPdfForUsageAnalyticsCategoryUsingAnalyticsDataFetcher()
    {
        var report = CreateTestReport(1, ReportCategory.USAGE_ANALYTICS, ReportType.PDF);
        _repoMock.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(report);
        _repoMock.Setup(r => r.UpdateAsync(It.IsAny<Report>())).ReturnsAsync((Report r) => r);

        var data = CreateSampleData();
        _fetcherMock.Setup(f => f.FetchAnalyticsDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(data);

        string filePath = Path.Combine(_outputDir, "test.pdf");
        File.WriteAllText(filePath, "test");
        _pdfMock.Setup(g => g.GeneratePdf(It.IsAny<Report>(), data, _outputDir)).Returns(filePath);

        await _worker.ProcessReportAsync(1);

        _fetcherMock.Verify(f => f.FetchAnalyticsDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null), Times.Once);
        _pdfMock.Verify(g => g.GeneratePdf(It.IsAny<Report>(), data, _outputDir), Times.Once);
    }

    [Fact]
    public async Task GeneratesCsvForAuditLogCategoryUsingAuditDataFetcher()
    {
        var report = CreateTestReport(2, ReportCategory.AUDIT_LOG, ReportType.CSV);
        _repoMock.Setup(r => r.GetByIdAsync(2)).ReturnsAsync(report);
        _repoMock.Setup(r => r.UpdateAsync(It.IsAny<Report>())).ReturnsAsync((Report r) => r);

        var data = CreateSampleData();
        _fetcherMock.Setup(f => f.FetchAuditDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(data);

        string filePath = Path.Combine(_outputDir, "test.csv");
        File.WriteAllText(filePath, "test");
        _csvMock.Setup(g => g.GenerateCsv(It.IsAny<Report>(), data, _outputDir)).Returns(filePath);

        await _worker.ProcessReportAsync(2);

        _fetcherMock.Verify(f => f.FetchAuditDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null), Times.Once);
        _csvMock.Verify(g => g.GenerateCsv(It.IsAny<Report>(), data, _outputDir), Times.Once);
    }

    [Fact]
    public async Task GeneratesExcelForUserActivityCategoryUsingUserActivityDataFetcher()
    {
        var report = CreateTestReport(3, ReportCategory.USER_ACTIVITY, ReportType.EXCEL);
        _repoMock.Setup(r => r.GetByIdAsync(3)).ReturnsAsync(report);
        _repoMock.Setup(r => r.UpdateAsync(It.IsAny<Report>())).ReturnsAsync((Report r) => r);

        var data = CreateSampleData();
        _fetcherMock.Setup(f => f.FetchUserActivityDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(data);

        string filePath = Path.Combine(_outputDir, "test.xlsx");
        File.WriteAllText(filePath, "test");
        _excelMock.Setup(g => g.GenerateExcel(It.IsAny<Report>(), data, _outputDir)).Returns(filePath);

        await _worker.ProcessReportAsync(3);

        _fetcherMock.Verify(f => f.FetchUserActivityDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null), Times.Once);
        _excelMock.Verify(g => g.GenerateExcel(It.IsAny<Report>(), data, _outputDir), Times.Once);
    }

    [Fact]
    public async Task SetsStatusToCompletedWithFileMetadataOnSuccess()
    {
        var report = CreateTestReport(4, ReportCategory.USAGE_ANALYTICS, ReportType.PDF);
        _repoMock.Setup(r => r.GetByIdAsync(4)).ReturnsAsync(report);
        _repoMock.Setup(r => r.UpdateAsync(It.IsAny<Report>())).ReturnsAsync((Report r) => r);

        var data = CreateSampleData();
        _fetcherMock.Setup(f => f.FetchAnalyticsDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(data);

        string filePath = Path.Combine(_outputDir, "test.pdf");
        File.WriteAllText(filePath, "pdf-content-here");
        _pdfMock.Setup(g => g.GeneratePdf(It.IsAny<Report>(), data, _outputDir)).Returns(filePath);

        await _worker.ProcessReportAsync(4);

        report.Status.Should().Be(ReportStatus.COMPLETED);
        report.CompletedAt.Should().NotBeNull();
        report.FilePath.Should().Be(filePath);
        report.FileSizeBytes.Should().BeGreaterThan(0);
        report.RowCount.Should().Be(10);
    }

    [Fact]
    public async Task SetsStatusToFailedWithErrorMessageOnException()
    {
        var report = CreateTestReport(5, ReportCategory.USAGE_ANALYTICS, ReportType.PDF);
        _repoMock.Setup(r => r.GetByIdAsync(5)).ReturnsAsync(report);
        _repoMock.Setup(r => r.UpdateAsync(It.IsAny<Report>())).ReturnsAsync((Report r) => r);

        _fetcherMock.Setup(f => f.FetchAnalyticsDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ThrowsAsync(new InvalidOperationException("Fetch failed"));

        await _worker.ProcessReportAsync(5);

        report.Status.Should().Be(ReportStatus.FAILED);
        report.ErrorMessage.Should().Contain("Fetch failed");
    }

    [Fact]
    public async Task TruncatesDataToMaxRowsWhenExceeded()
    {
        var report = CreateTestReport(6, ReportCategory.USAGE_ANALYTICS, ReportType.PDF);
        _repoMock.Setup(r => r.GetByIdAsync(6)).ReturnsAsync(report);
        _repoMock.Setup(r => r.UpdateAsync(It.IsAny<Report>())).ReturnsAsync((Report r) => r);

        // Reconfigure settings to have low MaxRows
        var channel = Channel.CreateUnbounded<long>();
        var logger = new Mock<ILogger<ReportGenerationWorker>>();
        var settings = Options.Create(new ReportSettings { MaxRows = 5, OutputDir = _outputDir });

        var services = new ServiceCollection();
        services.AddScoped(_ => _repoMock.Object);
        services.AddScoped(_ => _fetcherMock.Object);
        services.AddScoped(_ => _pdfMock.Object);
        services.AddScoped(_ => _csvMock.Object);
        services.AddScoped(_ => _excelMock.Object);
        var provider = services.BuildServiceProvider();

        var scopeFactory2 = provider.GetRequiredService<IServiceScopeFactory>();
        var worker = new ReportGenerationWorker(channel, scopeFactory2, logger.Object, settings);

        var data = CreateSampleData(20);
        _fetcherMock.Setup(f => f.FetchAnalyticsDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(data);

        string filePath = Path.Combine(_outputDir, "test.pdf");
        File.WriteAllText(filePath, "test");
        _pdfMock.Setup(g => g.GeneratePdf(It.IsAny<Report>(), It.Is<List<Dictionary<string, object>>>(d => d.Count == 5), _outputDir))
            .Returns(filePath);

        await worker.ProcessReportAsync(6);

        report.RowCount.Should().Be(5);
    }

    [Fact]
    public async Task HandlesMissingReportIdGracefully()
    {
        _repoMock.Setup(r => r.GetByIdAsync(999)).ReturnsAsync((Report?)null);
        await _worker.ProcessReportAsync(999);
        _repoMock.Verify(r => r.UpdateAsync(It.IsAny<Report>()), Times.Never);
    }

    [Fact]
    public async Task RoutesCollaborationMetricsToAnalyticsData()
    {
        var report = CreateTestReport(7, ReportCategory.COLLABORATION_METRICS, ReportType.PDF);
        _repoMock.Setup(r => r.GetByIdAsync(7)).ReturnsAsync(report);
        _repoMock.Setup(r => r.UpdateAsync(It.IsAny<Report>())).ReturnsAsync((Report r) => r);

        var data = CreateSampleData();
        _fetcherMock.Setup(f => f.FetchAnalyticsDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(data);

        string filePath = Path.Combine(_outputDir, "test.pdf");
        File.WriteAllText(filePath, "test");
        _pdfMock.Setup(g => g.GeneratePdf(It.IsAny<Report>(), data, _outputDir)).Returns(filePath);

        await _worker.ProcessReportAsync(7);

        _fetcherMock.Verify(f => f.FetchAnalyticsDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null), Times.Once);
    }

    [Fact]
    public async Task RoutesComplianceToAuditData()
    {
        var report = CreateTestReport(8, ReportCategory.COMPLIANCE, ReportType.CSV);
        _repoMock.Setup(r => r.GetByIdAsync(8)).ReturnsAsync(report);
        _repoMock.Setup(r => r.UpdateAsync(It.IsAny<Report>())).ReturnsAsync((Report r) => r);

        var data = CreateSampleData();
        _fetcherMock.Setup(f => f.FetchAuditDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(data);

        string filePath = Path.Combine(_outputDir, "test.csv");
        File.WriteAllText(filePath, "test");
        _csvMock.Setup(g => g.GenerateCsv(It.IsAny<Report>(), data, _outputDir)).Returns(filePath);

        await _worker.ProcessReportAsync(8);

        _fetcherMock.Verify(f => f.FetchAuditDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null), Times.Once);
    }

    [Fact]
    public async Task RoutesStorageSummaryToUserActivityData()
    {
        var report = CreateTestReport(9, ReportCategory.STORAGE_SUMMARY, ReportType.EXCEL);
        _repoMock.Setup(r => r.GetByIdAsync(9)).ReturnsAsync(report);
        _repoMock.Setup(r => r.UpdateAsync(It.IsAny<Report>())).ReturnsAsync((Report r) => r);

        var data = CreateSampleData();
        _fetcherMock.Setup(f => f.FetchUserActivityDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(data);

        string filePath = Path.Combine(_outputDir, "test.xlsx");
        File.WriteAllText(filePath, "test");
        _excelMock.Setup(g => g.GenerateExcel(It.IsAny<Report>(), data, _outputDir)).Returns(filePath);

        await _worker.ProcessReportAsync(9);

        _fetcherMock.Verify(f => f.FetchUserActivityDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null), Times.Once);
    }
}
