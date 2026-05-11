using FluentAssertions;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Repositories;
using OtterWorks.ReportService.Services;

namespace ReportService.Tests.Services;

public class ReportServiceTests
{
    private readonly Mock<IReportRepository> _repository;
    private readonly Mock<IReportGenerationWorker> _worker;
    private readonly OtterWorks.ReportService.Services.ReportService _service;

    public ReportServiceTests()
    {
        _repository = new Mock<IReportRepository>();
        _worker = new Mock<IReportGenerationWorker>();
        var logger = new Mock<ILogger<OtterWorks.ReportService.Services.ReportService>>();
        _service = new OtterWorks.ReportService.Services.ReportService(
            _repository.Object, _worker.Object, logger.Object);
    }

    [Fact]
    public async Task CreateReport_ShouldSaveWithPendingStatus()
    {
        var request = new ReportRequest
        {
            ReportName = "Test Report",
            Category = ReportCategory.USAGE_ANALYTICS,
            ReportType = ReportType.PDF,
            RequestedBy = "test-user",
            DateFrom = DateTime.UtcNow.AddDays(-7),
            DateTo = DateTime.UtcNow
        };

        _repository.Setup(r => r.CreateAsync(It.IsAny<Report>()))
            .ReturnsAsync((Report r) => { r.Id = 1; return r; });

        var result = await _service.CreateReportAsync(request);

        result.Status.Should().Be(ReportStatus.PENDING);
        result.ReportName.Should().Be("Test Report");
        result.RequestedBy.Should().Be("test-user");
        _worker.Verify(w => w.EnqueueReport(1), Times.Once);
    }

    [Fact]
    public async Task CreateReport_WithNullDateFrom_ShouldDefaultTo30DaysAgo()
    {
        var request = new ReportRequest
        {
            ReportName = "Test Report",
            Category = ReportCategory.AUDIT_LOG,
            ReportType = ReportType.CSV,
            RequestedBy = "test-user",
            DateFrom = null,
            DateTo = null
        };

        _repository.Setup(r => r.CreateAsync(It.IsAny<Report>()))
            .ReturnsAsync((Report r) => { r.Id = 2; return r; });

        var result = await _service.CreateReportAsync(request);

        result.DateFrom.Should().BeCloseTo(DateTime.UtcNow.AddDays(-30), TimeSpan.FromSeconds(5));
        result.DateTo.Should().BeCloseTo(DateTime.UtcNow, TimeSpan.FromSeconds(5));
    }

    [Fact]
    public async Task GetReport_ShouldReturnNullForNonexistent()
    {
        _repository.Setup(r => r.GetByIdAsync(99999)).ReturnsAsync((Report?)null);

        var result = await _service.GetReportAsync(99999);

        result.Should().BeNull();
    }

    [Fact]
    public async Task GetReportsByUser_ShouldDelegateToRepository()
    {
        var reports = new List<Report>
        {
            new() { Id = 1, ReportName = "Report 1", RequestedBy = "user-A", Status = ReportStatus.COMPLETED, CreatedAt = DateTime.UtcNow }
        };
        _repository.Setup(r => r.GetByUserAsync("user-A")).ReturnsAsync(reports);

        var result = await _service.GetReportsByUserAsync("user-A");

        result.Should().HaveCount(1);
        _repository.Verify(r => r.GetByUserAsync("user-A"), Times.Once);
    }

    [Fact]
    public async Task GetReportsByStatus_ShouldDelegateToRepository()
    {
        var reports = new List<Report>();
        _repository.Setup(r => r.GetByStatusAsync(ReportStatus.PENDING)).ReturnsAsync(reports);

        var result = await _service.GetReportsByStatusAsync(ReportStatus.PENDING);

        result.Should().BeEmpty();
        _repository.Verify(r => r.GetByStatusAsync(ReportStatus.PENDING), Times.Once);
    }

    [Fact]
    public async Task DeleteReport_ShouldReturnFalseForNonexistent()
    {
        _repository.Setup(r => r.GetByIdAsync(99999)).ReturnsAsync((Report?)null);

        var result = await _service.DeleteReportAsync(99999);

        result.Should().BeFalse();
    }

    [Fact]
    public async Task DeleteReport_ShouldDeleteFileAfterDbDelete()
    {
        var tempFile = Path.GetTempFileName();
        File.WriteAllText(tempFile, "test content");

        var report = new Report
        {
            Id = 1,
            ReportName = "Test",
            Status = ReportStatus.COMPLETED,
            FilePath = tempFile,
            RequestedBy = "user",
            CreatedAt = DateTime.UtcNow
        };

        _repository.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(report);
        _repository.Setup(r => r.DeleteAsync(1)).ReturnsAsync(true);

        var result = await _service.DeleteReportAsync(1);

        result.Should().BeTrue();
        File.Exists(tempFile).Should().BeFalse();
    }
}
