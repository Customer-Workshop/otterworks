using OtterWorks.SearchService.Models;

namespace OtterWorks.SearchService.Services;

public interface IMeiliSearchService
{
    Task EnsureIndicesAsync();
    bool Ping();
    SearchResponse Search(string query, string? docType = null, string? ownerId = null, int page = 1, int pageSize = 20);
    SearchResponse AdvancedSearch(string? query = null, string? docType = null, string? ownerId = null, List<string>? tags = null, string? dateFrom = null, string? dateTo = null, int page = 1, int pageSize = 20);
    List<string> Suggest(string prefix, int size = 10);
    void IndexDocument(Dictionary<string, object?> document);
    void IndexFile(Dictionary<string, object?> fileData);
    bool DeleteDocument(string docType, string docId);
    Dictionary<string, object?> Reindex(List<Dictionary<string, object?>>? documents = null, List<Dictionary<string, object?>>? files = null);
}
