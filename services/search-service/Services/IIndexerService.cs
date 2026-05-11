namespace OtterWorks.SearchService.Services;

public interface IIndexerService
{
    Dictionary<string, string> IndexDocument(Dictionary<string, object?> payload);
    Dictionary<string, string> IndexFile(Dictionary<string, object?> payload);
    Dictionary<string, object?> Remove(string docType, string docId);
    Dictionary<string, object?> Reindex();
    Dictionary<string, object?>? ProcessEvent(Dictionary<string, object?> eventData);
}
