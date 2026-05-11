using System.Net.Http.Json;
using System.Text.Json;
using OtterWorks.SearchService.Models;

namespace OtterWorks.SearchService.Services;

public class Indexer : IIndexer
{
    private readonly IMeilisearchService _search;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<Indexer> _logger;
    private const string DocumentServiceUrl = "http://document-service:8083";
    private const string FileServiceUrl = "http://file-service:8082";
    private const int FetchTimeout = 30;

    public Indexer(
        IMeilisearchService search,
        IHttpClientFactory httpClientFactory,
        ILogger<Indexer> logger)
    {
        _search = search;
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public async Task<IndexResult> IndexDocumentAsync(IndexDocumentRequest request, CancellationToken ct = default)
    {
        if (string.IsNullOrEmpty(request.Id))
        {
            throw new ArgumentException("Document 'id' is required");
        }

        if (string.IsNullOrEmpty(request.Title))
        {
            throw new ArgumentException("Document 'title' is required");
        }

        var document = new Dictionary<string, object?>
        {
            ["id"] = request.Id,
            ["title"] = request.Title,
            ["content"] = request.Content,
            ["owner_id"] = request.OwnerId,
            ["tags"] = request.Tags,
            ["created_at"] = request.CreatedAt,
            ["updated_at"] = request.UpdatedAt,
        };

        await _search.IndexDocumentAsync(document, ct);
        _logger.LogInformation("Indexer document indexed: {DocumentId}", request.Id);
        return new IndexResult { Status = "indexed", Id = request.Id, Type = "document" };
    }

    public async Task<IndexResult> IndexFileAsync(IndexFileRequest request, CancellationToken ct = default)
    {
        if (string.IsNullOrEmpty(request.Id))
        {
            throw new ArgumentException("File 'id' is required");
        }

        if (string.IsNullOrEmpty(request.Name))
        {
            throw new ArgumentException("File 'name' is required");
        }

        var fileData = new Dictionary<string, object?>
        {
            ["id"] = request.Id,
            ["name"] = request.Name,
            ["mime_type"] = request.MimeType,
            ["owner_id"] = request.OwnerId,
            ["folder_id"] = request.FolderId,
            ["tags"] = request.Tags,
            ["size"] = request.Size,
            ["created_at"] = request.CreatedAt,
            ["updated_at"] = request.UpdatedAt,
        };

        await _search.IndexFileAsync(fileData, ct);
        _logger.LogInformation("Indexer file indexed: {FileId}", request.Id);
        return new IndexResult { Status = "indexed", Id = request.Id, Type = "file" };
    }

    public async Task<IndexResult> RemoveAsync(string docType, string docId, CancellationToken ct = default)
    {
        if (docType is not ("document" or "file"))
        {
            throw new ArgumentException($"Invalid type '{docType}'. Must be 'document' or 'file'.");
        }

        var deleted = await _search.DeleteDocumentAsync(docType, docId, ct);
        var status = deleted ? "deleted" : "not_found";
        _logger.LogInformation("Indexer document removed: {DocId} type={DocType} status={Status}", docId, docType, status);
        return new IndexResult { Status = status, Id = docId, Type = docType };
    }

    public async Task<ReindexResult> ReindexAsync(CancellationToken ct = default)
    {
        var documents = await FetchAllDocumentsAsync(ct);
        var files = await FetchAllFilesAsync(ct);
        var result = await _search.ReindexAsync(documents, files, ct);
        _logger.LogInformation("Indexer reindex complete: documents={DocCount} files={FileCount}", documents.Count, files.Count);
        return result;
    }

    public async Task<IndexResult?> ProcessEventAsync(Dictionary<string, object?> eventData, CancellationToken ct = default)
    {
        var action = eventData.TryGetValue("action", out var actionObj) ? actionObj?.ToString() ?? string.Empty : string.Empty;
        var data = eventData.TryGetValue("data", out var dataObj) && dataObj is JsonElement dataEl
            ? JsonSerializer.Deserialize<Dictionary<string, object?>>(dataEl.GetRawText())
            : eventData.TryGetValue("data", out var dataDict) && dataDict is Dictionary<string, object?> dd ? dd : new Dictionary<string, object?>();

        return action switch
        {
            "index_document" => await IndexDocumentAsync(MapToDocumentRequest(data ?? new Dictionary<string, object?>()), ct),
            "index_file" => await IndexFileAsync(MapToFileRequest(data ?? new Dictionary<string, object?>()), ct),
            "delete" => await RemoveAsync(
                GetStringValue(data ?? new Dictionary<string, object?>(), "type", "document"),
                GetStringValue(data ?? new Dictionary<string, object?>(), "id", string.Empty),
                ct),
            _ => LogAndReturnNull(action),
        };
    }

    private IndexResult? LogAndReturnNull(string action)
    {
        _logger.LogWarning("Indexer unknown action: {Action}", action);
        return null;
    }

    private static IndexDocumentRequest MapToDocumentRequest(Dictionary<string, object?> data) => new()
    {
        Id = GetStringValue(data, "id"),
        Title = GetStringValue(data, "title"),
        Content = GetStringValue(data, "content"),
        OwnerId = GetStringValue(data, "owner_id"),
        Tags = GetListValue(data, "tags"),
        CreatedAt = GetStringValue(data, "created_at"),
        UpdatedAt = GetStringValue(data, "updated_at"),
    };

    private static IndexFileRequest MapToFileRequest(Dictionary<string, object?> data) => new()
    {
        Id = GetStringValue(data, "id"),
        Name = GetStringValue(data, "name"),
        MimeType = GetStringValue(data, "mime_type"),
        OwnerId = GetStringValue(data, "owner_id"),
        FolderId = GetStringValue(data, "folder_id"),
        Tags = GetListValue(data, "tags"),
        Size = GetIntValue(data, "size"),
        CreatedAt = GetStringValue(data, "created_at"),
        UpdatedAt = GetStringValue(data, "updated_at"),
    };

    private static string GetStringValue(Dictionary<string, object?> data, string key, string defaultValue = "")
    {
        if (!data.TryGetValue(key, out var value) || value is null)
        {
            return defaultValue;
        }

        if (value is JsonElement je)
        {
            return je.ValueKind == JsonValueKind.String ? je.GetString() ?? defaultValue : je.ToString();
        }

        return value.ToString() ?? defaultValue;
    }

    private static int GetIntValue(Dictionary<string, object?> data, string key, int defaultValue = 0)
    {
        if (!data.TryGetValue(key, out var value) || value is null)
        {
            return defaultValue;
        }

        if (value is JsonElement je && je.ValueKind == JsonValueKind.Number)
        {
            return je.GetInt32();
        }

        return int.TryParse(value.ToString(), out var result) ? result : defaultValue;
    }

    private static List<string> GetListValue(Dictionary<string, object?> data, string key)
    {
        if (!data.TryGetValue(key, out var value) || value is null)
        {
            return [];
        }

        if (value is JsonElement je && je.ValueKind == JsonValueKind.Array)
        {
            return je.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!).ToList();
        }

        if (value is List<string> list)
        {
            return list;
        }

        return [];
    }

    private async Task<List<Dictionary<string, object?>>> FetchAllDocumentsAsync(CancellationToken ct)
    {
        var docs = new List<Dictionary<string, object?>>();
        var page = 1;
        var client = _httpClientFactory.CreateClient();
        client.Timeout = TimeSpan.FromSeconds(FetchTimeout);

        while (true)
        {
            try
            {
                var response = await client.GetAsync($"{DocumentServiceUrl}/api/v1/documents/?page={page}&page_size=100", ct);
                if (!response.IsSuccessStatusCode)
                {
                    break;
                }

                var data = await response.Content.ReadFromJsonAsync<JsonElement>(ct);
                var items = GetItemsFromResponse(data, "documents");
                if (items.Count == 0)
                {
                    break;
                }

                foreach (var item in items)
                {
                    docs.Add(new Dictionary<string, object?>
                    {
                        ["id"] = GetJsonString(item, "id"),
                        ["title"] = GetJsonString(item, "title"),
                        ["content"] = GetJsonString(item, "content"),
                        ["owner_id"] = GetJsonString(item, "owner_id"),
                        ["tags"] = GetJsonStringArray(item, "tags"),
                        ["created_at"] = GetJsonString(item, "created_at"),
                        ["updated_at"] = GetJsonString(item, "updated_at"),
                        ["type"] = "document",
                    });
                }

                page++;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error fetching documents for reindex");
                break;
            }
        }

        return docs;
    }

    private async Task<List<Dictionary<string, object?>>> FetchAllFilesAsync(CancellationToken ct)
    {
        var files = new List<Dictionary<string, object?>>();
        var page = 1;
        var client = _httpClientFactory.CreateClient();
        client.Timeout = TimeSpan.FromSeconds(FetchTimeout);

        while (true)
        {
            try
            {
                var response = await client.GetAsync($"{FileServiceUrl}/api/v1/files?page={page}&page_size=100", ct);
                if (!response.IsSuccessStatusCode)
                {
                    break;
                }

                var data = await response.Content.ReadFromJsonAsync<JsonElement>(ct);
                var items = GetItemsFromResponse(data, "files");
                if (items.Count == 0)
                {
                    break;
                }

                foreach (var item in items)
                {
                    files.Add(new Dictionary<string, object?>
                    {
                        ["id"] = GetJsonString(item, "id"),
                        ["name"] = GetJsonString(item, "name"),
                        ["mime_type"] = GetJsonString(item, "mime_type") ?? GetJsonString(item, "mimeType"),
                        ["owner_id"] = GetJsonString(item, "owner_id") ?? GetJsonString(item, "ownerId"),
                        ["folder_id"] = GetJsonString(item, "folder_id") ?? GetJsonString(item, "folderId"),
                        ["tags"] = GetJsonStringArray(item, "tags"),
                        ["size"] = GetJsonInt(item, "size") ?? GetJsonInt(item, "size_bytes") ?? GetJsonInt(item, "sizeBytes") ?? 0,
                        ["created_at"] = GetJsonString(item, "created_at") ?? GetJsonString(item, "createdAt"),
                        ["updated_at"] = GetJsonString(item, "updated_at") ?? GetJsonString(item, "updatedAt"),
                        ["type"] = "file",
                    });
                }

                page++;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error fetching files for reindex");
                break;
            }
        }

        return files;
    }

    private static List<JsonElement> GetItemsFromResponse(JsonElement data, string primaryKey)
    {
        foreach (var key in new[] { primaryKey, "items", "data" })
        {
            if (data.TryGetProperty(key, out var arr) && arr.ValueKind == JsonValueKind.Array)
            {
                return arr.EnumerateArray().ToList();
            }
        }

        return [];
    }

    private static string? GetJsonString(JsonElement element, string property)
    {
        if (element.TryGetProperty(property, out var val) && val.ValueKind == JsonValueKind.String)
        {
            return val.GetString();
        }

        return null;
    }

    private static int? GetJsonInt(JsonElement element, string property)
    {
        if (element.TryGetProperty(property, out var val) && val.ValueKind == JsonValueKind.Number)
        {
            return val.GetInt32();
        }

        return null;
    }

    private static List<string> GetJsonStringArray(JsonElement element, string property)
    {
        if (element.TryGetProperty(property, out var val) && val.ValueKind == JsonValueKind.Array)
        {
            return val.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!).ToList();
        }

        return [];
    }
}
