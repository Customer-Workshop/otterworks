using OtterWorks.SearchService.Models;

namespace OtterWorks.SearchService.Services;

public interface IMeilisearchService
{
    Task EnsureIndicesAsync(CancellationToken ct = default);
    Task<bool> PingAsync(CancellationToken ct = default);

    Task<SearchResponse> SearchAsync(
        string query,
        string? docType = null,
        string? ownerId = null,
        int page = 1,
        int pageSize = 20,
        CancellationToken ct = default);

    Task<SearchResponse> AdvancedSearchAsync(
        string? query = null,
        string? docType = null,
        string? ownerId = null,
        List<string>? tags = null,
        string? dateFrom = null,
        string? dateTo = null,
        int page = 1,
        int pageSize = 20,
        CancellationToken ct = default);

    Task<List<string>> SuggestAsync(string prefix, int size = 10, CancellationToken ct = default);

    Task IndexDocumentAsync(Dictionary<string, object?> document, CancellationToken ct = default);
    Task IndexFileAsync(Dictionary<string, object?> fileData, CancellationToken ct = default);
    Task<bool> DeleteDocumentAsync(string docType, string docId, CancellationToken ct = default);
    Task<ReindexResult> ReindexAsync(List<Dictionary<string, object?>>? documents = null, List<Dictionary<string, object?>>? files = null, CancellationToken ct = default);

    AnalyticsData GetAnalytics();
}
