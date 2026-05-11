using System.Threading.Channels;
using FluentAssertions;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.ReportService.Data;
using OtterWorks.ReportService.Models;

namespace OtterWorks.ReportService.Tests.Unit;

public class ReportServiceTests
{
    private readonly Mock<IReportRepository> _repoMock;
    private readonly Channel<long> _channel;
    private readonly Services.ReportService _service;

    public ReportServiceTests()
    {
        _repoMock = new Mock<IReportRepository>();
        _channel = Channel.CreateUnbounded<long>();
        var logger = new Mock<ILogger<Services.ReportService>>();
        _service = new Services.ReportService(_repoMock.Object, _channel, logger.Object);
    }

    [Fact]
    public async Task CreateReport_SavesEntityWithPendingStatusAndCorrectFields()
    {
        var request = new ReportRequest
        {
            ReportName = "Test Report",
            Category = ReportCategory.USAGE_ANALYTICS,
            ReportType = ReportType.PDF,
            RequestedBy = "user-001",
        };

        _repoMock.Setup(r => r.AddAsync(It.IsAny<Report>()))
            .ReturnsAsync((Report r) => { r.Id = 1; return r; });

        var result = await _service.CreateReportAsync(request);

        result.Status.Should().Be(ReportStatus.PENDING);
        result.ReportName.Should().Be("Test Report");
        result.Category.Should().Be(ReportCategory.USAGE_ANALYTICS);
        result.ReportType.Should().Be(ReportType.PDF);
        result.RequestedBy.Should().Be("user-001");
    }

    [Fact]
    public async Task CreateReport_DefaultsDateFromTo30DaysAgoWhenNull()
    {
        var request = new ReportRequest
        {
            ReportName = "Test",
            Category = ReportCategory.AUDIT_LOG,
            ReportType = ReportType.CSV,
            RequestedBy = "user-001",
        };

        _repoMock.Setup(r => r.AddAsync(It.IsAny<Report>()))
            .ReturnsAsync((Report r) => { r.Id = 1; return r; });

        var result = await _service.CreateReportAsync(request);

        result.DateFrom.Should().BeCloseTo(DateTime.UtcNow.AddDays(-30), TimeSpan.FromSeconds(5));
    }

    [Fact]
    public async Task CreateReport_DefaultsDateToToNowWhenNull()
    {
        var request = new ReportRequest
        {
            ReportName = "Test",
            Category = ReportCategory.AUDIT_LOG,
            ReportType = ReportType.CSV,
            RequestedBy = "user-001",
        };

        _repoMock.Setup(r => r.AddAsync(It.IsAny<Report>()))
            .ReturnsAsync((Report r) => { r.Id = 1; return r; });

        var result = await _service.CreateReportAsync(request);

        result.DateTo.Should().BeCloseTo(DateTime.UtcNow, TimeSpan.FromSeconds(5));
    }

    [Fact]
    public async Task CreateReport_SerializesParametersAsJson()
    {
        var request = new ReportRequest
        {
            ReportName = "Test",
            Category = ReportCategory.AUDIT_LOG,
            ReportType = ReportType.PDF,
            RequestedBy = "user-001",
            Parameters = new Dictionary<string, string> { { "metric", "cpu" } },
        };

        _repoMock.Setup(r => r.AddAsync(It.IsAny<Report>()))
            .ReturnsAsync((Report r) => { r.Id = 1; return r; });

        var result = await _service.CreateReportAsync(request);

        result.Parameters.Should().Contain("metric");
        result.Parameters.Should().Contain("cpu");
    }

    [Fact]
    public async Task GetReport_ReturnsEntityWhenExists()
    {
        var report = new Report { Id = 1, ReportName = "Test" };
        _repoMock.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(report);

        var result = await _service.GetReportAsync(1);

        result.Should().NotBeNull();
        result!.ReportName.Should().Be("Test");
    }

    [Fact]
    public async Task GetReport_ReturnsNullWhenNotFound()
    {
        _repoMock.Setup(r => r.GetByIdAsync(999)).ReturnsAsync((Report?)null);

        var result = await _service.GetReportAsync(999);

        result.Should().BeNull();
    }

    [Fact]
    public async Task GetReportsByUser_ReturnsListOrderedByCreatedAtDesc()
    {
        var reports = new List<Report>
        {
            new() { Id = 2, RequestedBy = "user-001", CreatedAt = DateTime.UtcNow },
            new() { Id = 1, RequestedBy = "user-001", CreatedAt = DateTime.UtcNow.AddDays(-1) },
        };
        _repoMock.Setup(r => r.GetByUserAsync("user-001")).ReturnsAsync(reports);

        var result = await _service.GetReportsByUserAsync("user-001");

        result.Should().HaveCount(2);
        result[0].Id.Should().Be(2);
    }

    [Fact]
    public async Task GetReportsByStatus_ReturnsListOrderedByCreatedAtAsc()
    {
        var reports = new List<Report>
        {
            new() { Id = 1, Status = ReportStatus.PENDING, CreatedAt = DateTime.UtcNow.AddDays(-1) },
            new() { Id = 2, Status = ReportStatus.PENDING, CreatedAt = DateTime.UtcNow },
        };
        _repoMock.Setup(r => r.GetByStatusAsync(ReportStatus.PENDING)).ReturnsAsync(reports);

        var result = await _service.GetReportsByStatusAsync(ReportStatus.PENDING);

        result.Should().HaveCount(2);
        result[0].Id.Should().Be(1);
    }

    [Fact]
    public async Task DeleteReport_ReturnsTrueAndDeletesDbRecordWhenFound()
    {
        var report = new Report { Id = 1, ReportName = "Test" };
        _repoMock.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(report);
        _repoMock.Setup(r => r.DeleteAsync(1)).ReturnsAsync(true);

        var result = await _service.DeleteReportAsync(1);

        result.Should().BeTrue();
        _repoMock.Verify(r => r.DeleteAsync(1), Times.Once);
    }

    [Fact]
    public async Task DeleteReport_ReturnsFalseWhenNotFound()
    {
        _repoMock.Setup(r => r.GetByIdAsync(999)).ReturnsAsync((Report?)null);

        var result = await _service.DeleteReportAsync(999);

        result.Should().BeFalse();
    }

    [Fact]
    public async Task DeleteReport_DeletesFileFromDiskAfterDbDeletion()
    {
        string tempDir = Path.Combine(Path.GetTempPath(), "test-reports-" + Guid.NewGuid());
        Directory.CreateDirectory(tempDir);
        string filePath = Path.Combine(tempDir, "test.pdf");
        File.WriteAllText(filePath, "test content");

        var report = new Report { Id = 1, ReportName = "Test", FilePath = filePath };
        _repoMock.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(report);
        _repoMock.Setup(r => r.DeleteAsync(1)).ReturnsAsync(true);

        var result = await _service.DeleteReportAsync(1);

        result.Should().BeTrue();
        File.Exists(filePath).Should().BeFalse();

        Directory.Delete(tempDir, true);
    }
}
