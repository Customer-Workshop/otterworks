using OtterWorks.AnalyticsService.Models;

namespace OtterWorks.AnalyticsService.Services;

public interface IAnalyticsService
{
    Task<AnalyticsEvent> TrackEventAsync(
        string eventType,
        string userId,
        string resourceId,
        string resourceType,
        Dictionary<string, string> metadata);

    Task<DashboardSummary> GetDashboardSummaryAsync(string period);

    Task<UserActivity> GetUserActivityAsync(string userId);

    Task<DocumentStats> GetDocumentStatsAsync(string documentId);

    Task<TopContentResponse> GetTopContentAsync(string contentType, string period, int limit);

    Task<ActiveUsersResponse> GetActiveUsersAsync(string period);

    Task<StorageUsageResponse> GetStorageUsageAsync(string? userId);

    Task<ExportReportResponse> ExportReportAsync(string format, string period);

    Task<long> GetEventCountAsync();
}
