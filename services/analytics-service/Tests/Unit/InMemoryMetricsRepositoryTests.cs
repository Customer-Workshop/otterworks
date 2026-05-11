using OtterWorks.AnalyticsService.Models;
using OtterWorks.AnalyticsService.Services;

namespace AnalyticsService.Tests.Unit;

public class InMemoryMetricsRepositoryTests
{
    private readonly InMemoryMetricsRepository _repository = new();

    [Fact]
    public async Task StoreEvent_ShouldPersistEvent()
    {
        var analyticsEvent = AnalyticsEvent.Create(EventTypes.DocumentCreated, "user-1", "doc-1", "document");
        await _repository.StoreEventAsync(analyticsEvent);

        var count = await _repository.GetEventCountAsync();
        Assert.Equal(1, count);
    }

    [Fact]
    public async Task GetDashboardSummary_ShouldReturnEmptyForNoPeriodData()
    {
        var summary = await _repository.GetDashboardSummaryAsync("7d");

        Assert.Equal("7d", summary.Period);
        Assert.Equal(0, summary.TotalEvents);
        Assert.Equal(0, summary.DailyActiveUsers);
    }

    [Fact]
    public async Task GetUserActivity_ShouldReturnEmptyForUnknownUser()
    {
        var activity = await _repository.GetUserActivityAsync("unknown-user");

        Assert.Equal("unknown-user", activity.UserId);
        Assert.Equal(0, activity.TotalEvents);
        Assert.Empty(activity.RecentEvents);
    }

    [Fact]
    public async Task GetDocumentStats_ShouldReturnZerosForUnknownDocument()
    {
        var stats = await _repository.GetDocumentStatsAsync("unknown-doc");

        Assert.Equal("unknown-doc", stats.DocumentId);
        Assert.Equal(0, stats.Views);
        Assert.Equal(0, stats.Edits);
    }

    [Fact]
    public async Task GetActiveUsers_ShouldReturnEmptyListWhenNoEvents()
    {
        var response = await _repository.GetActiveUsersAsync("daily");

        Assert.Equal("daily", response.Period);
        Assert.Equal(0, response.Count);
        Assert.Empty(response.Users);
    }

    [Fact]
    public async Task GetStorageUsage_ShouldReturnZeroWhenNoEvents()
    {
        var response = await _repository.GetStorageUsageAsync(null);

        Assert.Equal(0, response.TotalStorageBytes);
        Assert.Equal(0, response.FilesCount);
    }

    [Fact]
    public async Task GetExportData_ShouldReturnEmptyListWhenNoEvents()
    {
        var data = await _repository.GetExportDataAsync("7d");

        Assert.Empty(data);
    }
}
