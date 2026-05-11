using OtterWorks.SearchService.Models;

namespace OtterWorks.SearchService.Services;

public interface IIndexer
{
    Task<IndexResult> IndexDocumentAsync(IndexDocumentRequest request, CancellationToken ct = default);
    Task<IndexResult> IndexFileAsync(IndexFileRequest request, CancellationToken ct = default);
    Task<IndexResult> RemoveAsync(string docType, string docId, CancellationToken ct = default);
    Task<ReindexResult> ReindexAsync(CancellationToken ct = default);
    Task<IndexResult?> ProcessEventAsync(Dictionary<string, object?> eventData, CancellationToken ct = default);
}
