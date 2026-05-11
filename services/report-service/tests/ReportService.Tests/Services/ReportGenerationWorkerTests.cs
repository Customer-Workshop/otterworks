using FluentAssertions;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;
using OtterWorks.ReportService.Config;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Repositories;
using OtterWorks.ReportService.Services;

namespace ReportService.Tests.Services;

public class ReportGenerationWorkerTests
{
    private readonly Mock<IReportRepository> _repository;
    private readonly Mock<IReportDataFetcher> _dataFetcher;
    private readonly Mock<IPdfReportGenerator> _pdfGenerator;
    private readonly Mock<ICsvReportGenerator> _csvGenerator;
    private readonly Mock<IExcelReportGenerator> _excelGenerator;
    private readonly string _outputDir;
    private readonly ReportGenerationWorker _worker;

    public ReportGenerationWorkerTests()
    {
        _repository = new Mock<IReportRepository>();
        _dataFetcher = new Mock<IReportDataFetcher>();
        _pdfGenerator = new Mock<IPdfReportGenerator>();
        _csvGenerator = new Mock<ICsvReportGenerator>();
        _excelGenerator = new Mock<IExcelReportGenerator>();
        _outputDir = Path.Combine(Path.GetTempPath(), "test-worker-" + Guid.NewGuid());
        Directory.CreateDirectory(_outputDir);

        var services = new ServiceCollection();
        services.AddScoped(_ => _repository.Object);
        services.AddScoped(_ => _dataFetcher.Object);
        services.AddScoped(_ => _pdfGenerator.Object);
        services.AddScoped(_ => _csvGenerator.Object);
        services.AddScoped(_ => _excelGenerator.Object);

        var serviceProvider = services.BuildServiceProvider();
        var scopeFactory = serviceProvider.GetRequiredService<IServiceScopeFactory>();

        var settings = Options.Create(new ReportSettings
        {
            OutputDir = _outputDir,
            MaxRows = 100
        });
        var logger = new Mock<ILogger<ReportGenerationWorker>>();

        _worker = new ReportGenerationWorker(scopeFactory, settings, logger.Object);
    }

    private Report CreatePendingReport(ReportType type = ReportType.PDF, ReportCategory category = ReportCategory.USAGE_ANALYTICS)
    {
        return new Report
        {
            Id = 1,
            ReportName = "Test Report",
            Category = category,
            ReportType = type,
            Status = ReportStatus.PENDING,
            RequestedBy = "test-user",
            CreatedAt = DateTime.UtcNow,
            DateFrom = DateTime.UtcNow.AddDays(-30),
            DateTo = DateTime.UtcNow
        };
    }

    private List<Dictionary<string, object>> CreateSampleData(int count = 10)
    {
        var data = new List<Dictionary<string, object>>();
        for (int i = 0; i < count; i++)
        {
            data.Add(new Dictionary<string, object> { ["id"] = i, ["value"] = $"item-{i}" });
        }
        return data;
    }

    [Fact]
    public async Task Worker_ShouldProcessPdfReport()
    {
        var report = CreatePendingReport();
        var tempFile = Path.Combine(_outputDir, "test.pdf");
        File.WriteAllText(tempFile, "fake pdf");

        _repository.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(report);
        _repository.Setup(r => r.UpdateAsync(It.IsAny<Report>())).Returns(Task.CompletedTask);
        _dataFetcher.Setup(d => d.FetchAnalyticsDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(CreateSampleData());
        _pdfGenerator.Setup(g => g.GeneratePdf(It.IsAny<Report>(), It.IsAny<List<Dictionary<string, object>>>(), _outputDir))
            .Returns(tempFile);

        _worker.EnqueueReport(1);

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var task = _worker.StartAsync(cts.Token);
        await Task.Delay(1000);
        await _worker.StopAsync(CancellationToken.None);

        _pdfGenerator.Verify(g => g.GeneratePdf(It.IsAny<Report>(), It.IsAny<List<Dictionary<string, object>>>(), _outputDir), Times.Once);
        report.Status.Should().Be(ReportStatus.COMPLETED);
    }

    [Fact]
    public async Task Worker_ShouldProcessCsvReport()
    {
        var report = CreatePendingReport(ReportType.CSV, ReportCategory.AUDIT_LOG);
        var tempFile = Path.Combine(_outputDir, "test.csv");
        File.WriteAllText(tempFile, "fake csv");

        _repository.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(report);
        _repository.Setup(r => r.UpdateAsync(It.IsAny<Report>())).Returns(Task.CompletedTask);
        _dataFetcher.Setup(d => d.FetchAuditDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(CreateSampleData());
        _csvGenerator.Setup(g => g.GenerateCsv(It.IsAny<Report>(), It.IsAny<List<Dictionary<string, object>>>(), _outputDir))
            .Returns(tempFile);

        _worker.EnqueueReport(1);

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        await _worker.StartAsync(cts.Token);
        await Task.Delay(1000);
        await _worker.StopAsync(CancellationToken.None);

        _csvGenerator.Verify(g => g.GenerateCsv(It.IsAny<Report>(), It.IsAny<List<Dictionary<string, object>>>(), _outputDir), Times.Once);
    }

    [Fact]
    public async Task Worker_ShouldProcessExcelReport()
    {
        var report = CreatePendingReport(ReportType.EXCEL, ReportCategory.USER_ACTIVITY);
        var tempFile = Path.Combine(_outputDir, "test.xlsx");
        File.WriteAllText(tempFile, "fake xlsx");

        _repository.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(report);
        _repository.Setup(r => r.UpdateAsync(It.IsAny<Report>())).Returns(Task.CompletedTask);
        _dataFetcher.Setup(d => d.FetchUserActivityDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(CreateSampleData());
        _excelGenerator.Setup(g => g.GenerateExcel(It.IsAny<Report>(), It.IsAny<List<Dictionary<string, object>>>(), _outputDir))
            .Returns(tempFile);

        _worker.EnqueueReport(1);

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        await _worker.StartAsync(cts.Token);
        await Task.Delay(1000);
        await _worker.StopAsync(CancellationToken.None);

        _excelGenerator.Verify(g => g.GenerateExcel(It.IsAny<Report>(), It.IsAny<List<Dictionary<string, object>>>(), _outputDir), Times.Once);
    }

    [Fact]
    public async Task Worker_OnFailure_ShouldSetFailedStatus()
    {
        var report = CreatePendingReport();

        _repository.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(report);
        _repository.Setup(r => r.UpdateAsync(It.IsAny<Report>())).Returns(Task.CompletedTask);
        _dataFetcher.Setup(d => d.FetchAnalyticsDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ThrowsAsync(new Exception("Fetch failed"));

        _worker.EnqueueReport(1);

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        await _worker.StartAsync(cts.Token);
        await Task.Delay(1000);
        await _worker.StopAsync(CancellationToken.None);

        report.Status.Should().Be(ReportStatus.FAILED);
        report.ErrorMessage.Should().Contain("Fetch failed");
    }

    [Fact]
    public async Task Worker_ShouldTruncateDataAtMaxRows()
    {
        var report = CreatePendingReport();
        var tempFile = Path.Combine(_outputDir, "test.pdf");
        File.WriteAllText(tempFile, "fake pdf");

        _repository.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(report);
        _repository.Setup(r => r.UpdateAsync(It.IsAny<Report>())).Returns(Task.CompletedTask);
        _dataFetcher.Setup(d => d.FetchAnalyticsDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(CreateSampleData(200)); // 200 rows, maxRows is 100
        _pdfGenerator.Setup(g => g.GeneratePdf(It.IsAny<Report>(),
                It.Is<List<Dictionary<string, object>>>(d => d.Count == 100), _outputDir))
            .Returns(tempFile);

        _worker.EnqueueReport(1);

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        await _worker.StartAsync(cts.Token);
        await Task.Delay(1000);
        await _worker.StopAsync(CancellationToken.None);

        _pdfGenerator.Verify(g => g.GeneratePdf(It.IsAny<Report>(),
            It.Is<List<Dictionary<string, object>>>(d => d.Count == 100), _outputDir), Times.Once);
    }

    [Fact]
    public async Task Worker_ShouldRouteCategoriesToCorrectFetcher()
    {
        // Test COMPLIANCE -> AuditData
        var report = CreatePendingReport(ReportType.PDF, ReportCategory.COMPLIANCE);
        var tempFile = Path.Combine(_outputDir, "test.pdf");
        File.WriteAllText(tempFile, "fake pdf");

        _repository.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(report);
        _repository.Setup(r => r.UpdateAsync(It.IsAny<Report>())).Returns(Task.CompletedTask);
        _dataFetcher.Setup(d => d.FetchAuditDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null))
            .ReturnsAsync(CreateSampleData());
        _pdfGenerator.Setup(g => g.GeneratePdf(It.IsAny<Report>(), It.IsAny<List<Dictionary<string, object>>>(), _outputDir))
            .Returns(tempFile);

        _worker.EnqueueReport(1);

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        await _worker.StartAsync(cts.Token);
        await Task.Delay(1000);
        await _worker.StopAsync(CancellationToken.None);

        _dataFetcher.Verify(d => d.FetchAuditDataAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), null), Times.Once);
    }
}
