using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.AnalyticsService.Controllers;
using OtterWorks.AnalyticsService.Models;
using OtterWorks.AnalyticsService.Services;

namespace AnalyticsService.Tests.Unit;

public class ControllerTests
{
    private readonly Mock<IAnalyticsService> _mockService;
    private readonly AnalyticsController _controller;

    public ControllerTests()
    {
        _mockService = new Mock<IAnalyticsService>();
        var logger = new Mock<ILogger<AnalyticsController>>();
        _controller = new AnalyticsController(_mockService.Object, logger.Object);
    }

    [Fact]
    public async Task TrackEvent_ShouldReturnAccepted()
    {
        var request = new TrackEventRequest
        {
            EventType = "document.created",
            UserId = "user-1",
            ResourceId = "doc-1",
            ResourceType = "document",
            Metadata = new Dictionary<string, string> { ["title"] = "Test" },
        };

        _mockService
            .Setup(s => s.TrackEventAsync(
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<Dictionary<string, string>>()))
            .ReturnsAsync(AnalyticsEvent.Create("document.created", "user-1", "doc-1", "document"));

        var result = await _controller.TrackEvent(request);

        var accepted = Assert.IsType<AcceptedResult>(result);
        var response = Assert.IsType<AcceptedResponse>(accepted.Value);
        Assert.Equal("accepted", response.Status);
        Assert.NotEmpty(response.EventId);
    }

    [Fact]
    public async Task GetDashboard_ShouldReturnOkWithSummary()
    {
        _mockService
            .Setup(s => s.GetDashboardSummaryAsync("7d"))
            .ReturnsAsync(new DashboardSummary { Period = "7d", TotalEvents = 0 });

        var result = await _controller.GetDashboard("7d");

        var ok = Assert.IsType<OkObjectResult>(result);
        var summary = Assert.IsType<DashboardSummary>(ok.Value);
        Assert.Equal("7d", summary.Period);
        Assert.Equal(0, summary.TotalEvents);
    }

    [Fact]
    public async Task GetDashboard_ShouldAcceptPeriodParameter()
    {
        _mockService
            .Setup(s => s.GetDashboardSummaryAsync("30d"))
            .ReturnsAsync(new DashboardSummary { Period = "30d" });

        var result = await _controller.GetDashboard("30d");

        var ok = Assert.IsType<OkObjectResult>(result);
        var summary = Assert.IsType<DashboardSummary>(ok.Value);
        Assert.Equal("30d", summary.Period);
    }

    [Fact]
    public async Task GetUserActivity_ShouldReturnOk()
    {
        _mockService
            .Setup(s => s.GetUserActivityAsync("user-42"))
            .ReturnsAsync(new UserActivity { UserId = "user-42", TotalEvents = 1 });

        var result = await _controller.GetUserActivity("user-42");

        var ok = Assert.IsType<OkObjectResult>(result);
        var activity = Assert.IsType<UserActivity>(ok.Value);
        Assert.Equal("user-42", activity.UserId);
        Assert.Equal(1, activity.TotalEvents);
    }

    [Fact]
    public async Task GetDocumentStats_ShouldReturnOk()
    {
        _mockService
            .Setup(s => s.GetDocumentStatsAsync("doc-99"))
            .ReturnsAsync(new DocumentStats { DocumentId = "doc-99", Views = 1 });

        var result = await _controller.GetDocumentStats("doc-99");

        var ok = Assert.IsType<OkObjectResult>(result);
        var stats = Assert.IsType<DocumentStats>(ok.Value);
        Assert.Equal("doc-99", stats.DocumentId);
        Assert.Equal(1, stats.Views);
    }

    [Fact]
    public async Task GetTopContent_ShouldReturnOk()
    {
        _mockService
            .Setup(s => s.GetTopContentAsync("documents", "7d", 10))
            .ReturnsAsync(new TopContentResponse { ContentType = "documents", Period = "7d" });

        var result = await _controller.GetTopContent("documents", "7d", 10);

        var ok = Assert.IsType<OkObjectResult>(result);
        var response = Assert.IsType<TopContentResponse>(ok.Value);
        Assert.Equal("documents", response.ContentType);
        Assert.Equal("7d", response.Period);
    }

    [Fact]
    public async Task GetActiveUsers_ShouldReturnOk()
    {
        _mockService
            .Setup(s => s.GetActiveUsersAsync("daily"))
            .ReturnsAsync(new ActiveUsersResponse { Period = "daily", Count = 0 });

        var result = await _controller.GetActiveUsers("daily");

        var ok = Assert.IsType<OkObjectResult>(result);
        var response = Assert.IsType<ActiveUsersResponse>(ok.Value);
        Assert.Equal("daily", response.Period);
        Assert.Equal(0, response.Count);
    }

    [Fact]
    public async Task GetStorageUsage_ShouldReturnOk()
    {
        _mockService
            .Setup(s => s.GetStorageUsageAsync(null))
            .ReturnsAsync(new StorageUsageResponse { TotalStorageBytes = 0 });

        var result = await _controller.GetStorageUsage();

        var ok = Assert.IsType<OkObjectResult>(result);
        var response = Assert.IsType<StorageUsageResponse>(ok.Value);
        Assert.Equal(0, response.TotalStorageBytes);
    }

    [Fact]
    public async Task GetStorageUsage_ShouldFilterByUserId()
    {
        _mockService
            .Setup(s => s.GetStorageUsageAsync("user-1"))
            .ReturnsAsync(new StorageUsageResponse { UserId = "user-1", TotalStorageBytes = 512 });

        var result = await _controller.GetStorageUsage("user-1");

        var ok = Assert.IsType<OkObjectResult>(result);
        var response = Assert.IsType<StorageUsageResponse>(ok.Value);
        Assert.Equal("user-1", response.UserId);
        Assert.Equal(512, response.TotalStorageBytes);
    }

    [Fact]
    public async Task ExportReport_ShouldReturnJsonExport()
    {
        _mockService
            .Setup(s => s.ExportReportAsync("json", "7d"))
            .ReturnsAsync(new ExportReportResponse { Format = "json", RecordCount = 1 });

        var result = await _controller.ExportReport("json", "7d");

        var ok = Assert.IsType<OkObjectResult>(result);
        var response = Assert.IsType<ExportReportResponse>(ok.Value);
        Assert.Equal("json", response.Format);
        Assert.Equal(1, response.RecordCount);
    }

    [Fact]
    public async Task ExportReport_ShouldReturnCsvExport()
    {
        _mockService
            .Setup(s => s.ExportReportAsync("csv", "7d"))
            .ReturnsAsync(new ExportReportResponse
            {
                Format = "csv",
                RecordCount = 1,
                Data = new List<Dictionary<string, string>>
                {
                    new()
                    {
                        ["event_id"] = "evt-1",
                        ["event_type"] = "document.created",
                        ["user_id"] = "user-1",
                        ["resource_id"] = "doc-1",
                        ["resource_type"] = "document",
                        ["timestamp"] = "2024-01-01T00:00:00Z",
                    },
                },
            });

        var result = await _controller.ExportReport("csv", "7d");

        var content = Assert.IsType<ContentResult>(result);
        Assert.Contains("event_id,event_type,user_id,resource_id,resource_type,timestamp", content.Content);
        Assert.Contains("document.created", content.Content);
    }
}
