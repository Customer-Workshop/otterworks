using OtterWorks.AnalyticsService.Models;

namespace OtterWorks.AnalyticsService.Services;

public class AnalyticsService : IAnalyticsService
{
    private readonly IMetricsRepository _repository;
    private readonly ILogger<AnalyticsService> _logger;

    public AnalyticsService(IMetricsRepository repository, ILogger<AnalyticsService> logger)
    {
        _repository = repository;
        _logger = logger;
    }

    public async Task<AnalyticsEvent> TrackEventAsync(
        string eventType,
        string userId,
        string resourceId,
        string resourceType,
        Dictionary<string, string> metadata)
    {
        var analyticsEvent = AnalyticsEvent.Create(eventType, userId, resourceId, resourceType, metadata);
        _logger.LogInformation(
            "Tracking event: type={EventType}, user={UserId}, resource={ResourceId}",
            analyticsEvent.EventType,
            analyticsEvent.UserId,
            analyticsEvent.ResourceId);
        await _repository.StoreEventAsync(analyticsEvent);
        return analyticsEvent;
    }

    public async Task<DashboardSummary> GetDashboardSummaryAsync(string period)
    {
        _logger.LogDebug("Fetching dashboard summary for period={Period}", period);
        return await _repository.GetDashboardSummaryAsync(period);
    }

    public async Task<UserActivity> GetUserActivityAsync(string userId)
    {
        _logger.LogDebug("Fetching activity for user={UserId}", userId);
        return await _repository.GetUserActivityAsync(userId);
    }

    public async Task<DocumentStats> GetDocumentStatsAsync(string documentId)
    {
        _logger.LogDebug("Fetching stats for document={DocumentId}", documentId);
        return await _repository.GetDocumentStatsAsync(documentId);
    }

    public async Task<TopContentResponse> GetTopContentAsync(string contentType, string period, int limit)
    {
        _logger.LogDebug("Fetching top content: type={ContentType}, period={Period}, limit={Limit}", contentType, period, limit);
        return await _repository.GetTopContentAsync(contentType, period, limit);
    }

    public async Task<ActiveUsersResponse> GetActiveUsersAsync(string period)
    {
        _logger.LogDebug("Fetching active users for period={Period}", period);
        return await _repository.GetActiveUsersAsync(period);
    }

    public async Task<StorageUsageResponse> GetStorageUsageAsync(string? userId)
    {
        _logger.LogDebug("Fetching storage usage for userId={UserId}", userId);
        return await _repository.GetStorageUsageAsync(userId);
    }

    public async Task<ExportReportResponse> ExportReportAsync(string format, string period)
    {
        _logger.LogInformation("Exporting analytics report: format={Format}, period={Period}", format, period);
        var data = await _repository.GetExportDataAsync(period);
        return new ExportReportResponse
        {
            Format = format,
            Period = period,
            GeneratedAt = DateTime.UtcNow.ToString("o"),
            RecordCount = data.Count,
            Data = data,
        };
    }

    public async Task<long> GetEventCountAsync()
    {
        return await _repository.GetEventCountAsync();
    }
}
