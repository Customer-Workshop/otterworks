using OtterWorks.AnalyticsService.Models;

namespace OtterWorks.AnalyticsService.Services;

public interface IMetricsRepository
{
    Task StoreEventAsync(AnalyticsEvent analyticsEvent);

    Task<DashboardSummary> GetDashboardSummaryAsync(string period);

    Task<UserActivity> GetUserActivityAsync(string userId);

    Task<DocumentStats> GetDocumentStatsAsync(string documentId);

    Task<TopContentResponse> GetTopContentAsync(string contentType, string period, int limit);

    Task<ActiveUsersResponse> GetActiveUsersAsync(string period);

    Task<StorageUsageResponse> GetStorageUsageAsync(string? userId);

    Task<List<Dictionary<string, string>>> GetExportDataAsync(string period);

    Task<long> GetEventCountAsync();
}
