using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.AnalyticsService.Models;
using OtterWorks.AnalyticsService.Services;

namespace AnalyticsService.Tests.Unit;

public class AnalyticsServiceTests
{
    private readonly InMemoryMetricsRepository _repository;
    private readonly OtterWorks.AnalyticsService.Services.AnalyticsService _service;

    public AnalyticsServiceTests()
    {
        _repository = new InMemoryMetricsRepository();
        var logger = new Mock<ILogger<OtterWorks.AnalyticsService.Services.AnalyticsService>>();
        _service = new OtterWorks.AnalyticsService.Services.AnalyticsService(_repository, logger.Object);
    }

    [Fact]
    public async Task TrackEvent_ShouldCreateAndStoreEvent()
    {
        var result = await _service.TrackEventAsync(
            EventTypes.DocumentCreated,
            "user-1",
            "doc-1",
            "document",
            new Dictionary<string, string> { ["title"] = "Test Document" });

        Assert.Equal(EventTypes.DocumentCreated, result.EventType);
        Assert.Equal("user-1", result.UserId);
        Assert.Equal("doc-1", result.ResourceId);
        Assert.NotEmpty(result.EventId);
    }

    [Fact]
    public async Task GetDashboardSummary_ShouldReturnAggregatedMetrics()
    {
        await _service.TrackEventAsync(EventTypes.DocumentCreated, "user-1", "doc-1", "document", new Dictionary<string, string>());
        await _service.TrackEventAsync(EventTypes.DocumentCreated, "user-2", "doc-2", "document", new Dictionary<string, string>());
        await _service.TrackEventAsync(EventTypes.FileUploaded, "user-1", "file-1", "file", new Dictionary<string, string>());
        await _service.TrackEventAsync(EventTypes.CollabSessionStarted, "user-1", "session-1", "session", new Dictionary<string, string>());

        var summary = await _service.GetDashboardSummaryAsync("7d");

        Assert.Equal("7d", summary.Period);
        Assert.Equal(2, summary.DailyActiveUsers);
        Assert.Equal(2, summary.DocumentsCreated);
        Assert.Equal(1, summary.FilesUploaded);
        Assert.Equal(1, summary.CollabSessions);
        Assert.Equal(4, summary.TotalEvents);
    }

    [Fact]
    public async Task GetUserActivity_ShouldReturnActivityForSpecificUser()
    {
        await _service.TrackEventAsync(EventTypes.DocumentCreated, "user-1", "doc-1", "document", new Dictionary<string, string>());
        await _service.TrackEventAsync(EventTypes.DocumentViewed, "user-1", "doc-1", "document", new Dictionary<string, string>());
        await _service.TrackEventAsync(EventTypes.FileUploaded, "user-1", "file-1", "file", new Dictionary<string, string>());
        await _service.TrackEventAsync(EventTypes.DocumentCreated, "user-2", "doc-2", "document", new Dictionary<string, string>());

        var activity = await _service.GetUserActivityAsync("user-1");

        Assert.Equal("user-1", activity.UserId);
        Assert.Equal(3, activity.TotalEvents);
        Assert.Equal(1, activity.DocumentsCreated);
        Assert.Equal(1, activity.DocumentsViewed);
        Assert.Equal(1, activity.FilesUploaded);
        Assert.Equal(3, activity.RecentEvents.Count);
    }

    [Fact]
    public async Task GetDocumentStats_ShouldReturnDocumentLevelAnalytics()
    {
        await _service.TrackEventAsync(EventTypes.DocumentViewed, "user-1", "doc-1", "document", new Dictionary<string, string>());
        await _service.TrackEventAsync(EventTypes.DocumentViewed, "user-2", "doc-1", "document", new Dictionary<string, string>());
        await _service.TrackEventAsync(EventTypes.DocumentEdited, "user-1", "doc-1", "document", new Dictionary<string, string>());
        await _service.TrackEventAsync(EventTypes.DocumentShared, "user-1", "doc-1", "document", new Dictionary<string, string>());

        var stats = await _service.GetDocumentStatsAsync("doc-1");

        Assert.Equal("doc-1", stats.DocumentId);
        Assert.Equal(2, stats.Views);
        Assert.Equal(1, stats.Edits);
        Assert.Equal(1, stats.Shares);
        Assert.Equal(2, stats.UniqueViewers);
    }

    [Fact]
    public async Task GetTopContent_ShouldReturnContentRankedByActivity()
    {
        await _service.TrackEventAsync(EventTypes.DocumentViewed, "user-1", "doc-1", "document", new Dictionary<string, string> { ["title"] = "Popular" });
        await _service.TrackEventAsync(EventTypes.DocumentViewed, "user-2", "doc-1", "document", new Dictionary<string, string> { ["title"] = "Popular" });
        await _service.TrackEventAsync(EventTypes.DocumentEdited, "user-1", "doc-1", "document", new Dictionary<string, string> { ["title"] = "Popular" });
        await _service.TrackEventAsync(EventTypes.DocumentViewed, "user-1", "doc-2", "document", new Dictionary<string, string> { ["title"] = "Less Popular" });

        var response = await _service.GetTopContentAsync("documents", "7d", 10);

        Assert.Equal(2, response.Items.Count);
        Assert.Equal("doc-1", response.Items[0].ResourceId);
        Assert.Equal(3, response.Items[0].EventCount);
        Assert.Equal("doc-2", response.Items[1].ResourceId);
    }

    [Fact]
    public async Task GetActiveUsers_ShouldReturnUsersRankedByActivity()
    {
        await _service.TrackEventAsync(EventTypes.DocumentViewed, "user-1", "doc-1", "document", new Dictionary<string, string>());
        await _service.TrackEventAsync(EventTypes.DocumentViewed, "user-1", "doc-2", "document", new Dictionary<string, string>());
        await _service.TrackEventAsync(EventTypes.DocumentViewed, "user-2", "doc-1", "document", new Dictionary<string, string>());

        var response = await _service.GetActiveUsersAsync("daily");

        Assert.Equal(2, response.Count);
        Assert.Equal("user-1", response.Users[0].UserId);
        Assert.Equal(2, response.Users[0].EventCount);
    }

    [Fact]
    public async Task GetStorageUsage_ShouldCalculateStorageMetrics()
    {
        await _service.TrackEventAsync(EventTypes.StorageAllocated, "user-1", "file-1", "file", new Dictionary<string, string> { ["bytes"] = "1024" });
        await _service.TrackEventAsync(EventTypes.StorageAllocated, "user-1", "file-2", "file", new Dictionary<string, string> { ["bytes"] = "2048" });
        await _service.TrackEventAsync(EventTypes.FileUploaded, "user-1", "file-1", "file", new Dictionary<string, string>());

        var usage = await _service.GetStorageUsageAsync("user-1");

        Assert.Equal("user-1", usage.UserId);
        Assert.Equal(3072, usage.TotalStorageBytes);
        Assert.Equal(1, usage.FilesCount);
    }

    [Fact]
    public async Task ExportReport_ShouldReturnEventDataForPeriod()
    {
        await _service.TrackEventAsync(EventTypes.DocumentCreated, "user-1", "doc-1", "document", new Dictionary<string, string>());
        await _service.TrackEventAsync(EventTypes.FileUploaded, "user-1", "file-1", "file", new Dictionary<string, string>());

        var report = await _service.ExportReportAsync("json", "7d");

        Assert.Equal("json", report.Format);
        Assert.Equal("7d", report.Period);
        Assert.Equal(2, report.RecordCount);
        Assert.Equal(2, report.Data.Count);
        Assert.Contains("event_id", report.Data[0].Keys);
        Assert.Contains("event_type", report.Data[0].Keys);
        Assert.Contains("user_id", report.Data[0].Keys);
    }
}
