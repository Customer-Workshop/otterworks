namespace OtterWorks.SearchService.Services;

public class IndexerService : IIndexerService
{
    private readonly IMeiliSearchService _search;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly Serilog.ILogger _logger = Serilog.Log.ForContext<IndexerService>();

    private const string DocumentServiceUrl = "http://document-service:8083";
    private const string FileServiceUrl = "http://file-service:8082";
    private const int FetchTimeoutSeconds = 30;

    public IndexerService(IMeiliSearchService search, IHttpClientFactory httpClientFactory)
    {
        _search = search;
        _httpClientFactory = httpClientFactory;
    }

    public Dictionary<string, string> IndexDocument(Dictionary<string, object?> payload)
    {
        string? id = GetString(payload, "id");
        string? title = GetString(payload, "title");

        if (string.IsNullOrEmpty(id))
            throw new ArgumentException("Document 'id' is required");
        if (string.IsNullOrEmpty(title))
            throw new ArgumentException("Document 'title' is required");

        var document = new Dictionary<string, object?>
        {
            ["id"] = id,
            ["title"] = title,
            ["content"] = GetString(payload, "content") ?? string.Empty,
            ["owner_id"] = GetString(payload, "owner_id") ?? string.Empty,
            ["tags"] = GetTags(payload),
            ["created_at"] = GetString(payload, "created_at"),
            ["updated_at"] = GetString(payload, "updated_at"),
        };

        _search.IndexDocument(document);
        _logger.Information("Indexer document indexed: {DocumentId}", id);
        return new Dictionary<string, string>
        {
            ["status"] = "indexed",
            ["id"] = id,
            ["type"] = "document",
        };
    }

    public Dictionary<string, string> IndexFile(Dictionary<string, object?> payload)
    {
        string? id = GetString(payload, "id");
        string? name = GetString(payload, "name");

        if (string.IsNullOrEmpty(id))
            throw new ArgumentException("File 'id' is required");
        if (string.IsNullOrEmpty(name))
            throw new ArgumentException("File 'name' is required");

        var fileData = new Dictionary<string, object?>
        {
            ["id"] = id,
            ["name"] = name,
            ["mime_type"] = GetString(payload, "mime_type") ?? string.Empty,
            ["owner_id"] = GetString(payload, "owner_id") ?? string.Empty,
            ["folder_id"] = GetString(payload, "folder_id") ?? string.Empty,
            ["tags"] = GetTags(payload),
            ["size"] = GetInt(payload, "size"),
            ["created_at"] = GetString(payload, "created_at"),
            ["updated_at"] = GetString(payload, "updated_at"),
        };

        _search.IndexFile(fileData);
        _logger.Information("Indexer file indexed: {FileId}", id);
        return new Dictionary<string, string>
        {
            ["status"] = "indexed",
            ["id"] = id,
            ["type"] = "file",
        };
    }

    public Dictionary<string, object?> Remove(string docType, string docId)
    {
        if (docType is not "document" and not "file")
            throw new ArgumentException($"Invalid type '{docType}'. Must be 'document' or 'file'.");

        bool deleted = _search.DeleteDocument(docType, docId);
        string status = deleted ? "deleted" : "not_found";
        _logger.Information("Indexer document removed: {DocId} type={DocType} status={Status}", docId, docType, status);
        return new Dictionary<string, object?>
        {
            ["status"] = status,
            ["id"] = docId,
            ["type"] = docType,
        };
    }

    public Dictionary<string, object?> Reindex()
    {
        var documents = FetchAllDocuments();
        var files = FetchAllFiles();
        var result = _search.Reindex(documents: documents, files: files);
        _logger.Information("Indexer reindex complete: {Documents} documents, {Files} files", documents.Count, files.Count);
        return result;
    }

    public Dictionary<string, object?>? ProcessEvent(Dictionary<string, object?> eventData)
    {
        string action = GetString(eventData, "action") ?? string.Empty;
        var data = GetNestedDict(eventData, "data");

        return action switch
        {
            "index_document" => IndexDocument(data).ToDictionary(kv => kv.Key, kv => (object?)kv.Value),
            "index_file" => IndexFile(data).ToDictionary(kv => kv.Key, kv => (object?)kv.Value),
            "delete" => Remove(GetString(data, "type") ?? "document", GetString(data, "id") ?? string.Empty),
            _ => LogUnknownAction(action),
        };
    }

    private Dictionary<string, object?>? LogUnknownAction(string action)
    {
        _logger.Warning("Indexer unknown action: {Action}", action);
        return null;
    }

    private List<Dictionary<string, object?>> FetchAllDocuments()
    {
        var docs = new List<Dictionary<string, object?>>();
        int page = 1;
        var client = _httpClientFactory.CreateClient("DocumentService");

        while (true)
        {
            try
            {
                var response = client.GetAsync($"{DocumentServiceUrl}/api/v1/documents/?page={page}&page_size=100").GetAwaiter().GetResult();
                if (!response.IsSuccessStatusCode)
                {
                    _logger.Warning("Reindex document fetch failed with status {Status}", (int)response.StatusCode);
                    break;
                }

                var data = response.Content.ReadFromJsonAsync<Dictionary<string, System.Text.Json.JsonElement>>().GetAwaiter().GetResult();
                if (data is null) break;

                System.Text.Json.JsonElement items = default;
                bool found = data.TryGetValue("documents", out items) ||
                             data.TryGetValue("items", out items) ||
                             data.TryGetValue("data", out items);

                if (!found || items.ValueKind != System.Text.Json.JsonValueKind.Array || items.GetArrayLength() == 0)
                    break;

                foreach (var item in items.EnumerateArray())
                {
                    docs.Add(new Dictionary<string, object?>
                    {
                        ["id"] = item.GetProperty("id").GetString() ?? string.Empty,
                        ["title"] = GetJsonStr(item, "title"),
                        ["content"] = GetJsonStr(item, "content"),
                        ["owner_id"] = GetJsonStr(item, "owner_id"),
                        ["tags"] = GetJsonStrArray(item, "tags"),
                        ["created_at"] = GetJsonStrOrNull(item, "created_at"),
                        ["updated_at"] = GetJsonStrOrNull(item, "updated_at"),
                        ["type"] = "document",
                    });
                }

                page++;
            }
            catch (Exception ex)
            {
                _logger.Error(ex, "Reindex document fetch error");
                break;
            }
        }

        return docs;
    }

    private List<Dictionary<string, object?>> FetchAllFiles()
    {
        var files = new List<Dictionary<string, object?>>();
        int page = 1;
        var client = _httpClientFactory.CreateClient("FileService");

        while (true)
        {
            try
            {
                var response = client.GetAsync($"{FileServiceUrl}/api/v1/files?page={page}&page_size=100").GetAwaiter().GetResult();
                if (!response.IsSuccessStatusCode)
                {
                    _logger.Warning("Reindex file fetch failed with status {Status}", (int)response.StatusCode);
                    break;
                }

                var data = response.Content.ReadFromJsonAsync<Dictionary<string, System.Text.Json.JsonElement>>().GetAwaiter().GetResult();
                if (data is null) break;

                System.Text.Json.JsonElement items = default;
                bool found = data.TryGetValue("files", out items) ||
                             data.TryGetValue("items", out items) ||
                             data.TryGetValue("data", out items);

                if (!found || items.ValueKind != System.Text.Json.JsonValueKind.Array || items.GetArrayLength() == 0)
                    break;

                foreach (var item in items.EnumerateArray())
                {
                    files.Add(new Dictionary<string, object?>
                    {
                        ["id"] = GetJsonStr(item, "id"),
                        ["name"] = GetJsonStr(item, "name"),
                        ["mime_type"] = GetJsonStr(item, "mime_type") ?? GetJsonStr(item, "mimeType"),
                        ["owner_id"] = GetJsonStr(item, "owner_id") ?? GetJsonStr(item, "ownerId"),
                        ["folder_id"] = GetJsonStr(item, "folder_id") ?? GetJsonStr(item, "folderId"),
                        ["tags"] = GetJsonStrArray(item, "tags"),
                        ["size"] = GetJsonInt(item, "size") ?? GetJsonInt(item, "size_bytes") ?? GetJsonInt(item, "sizeBytes") ?? 0,
                        ["created_at"] = GetJsonStrOrNull(item, "created_at") ?? GetJsonStrOrNull(item, "createdAt"),
                        ["updated_at"] = GetJsonStrOrNull(item, "updated_at") ?? GetJsonStrOrNull(item, "updatedAt"),
                        ["type"] = "file",
                    });
                }

                page++;
            }
            catch (Exception ex)
            {
                _logger.Error(ex, "Reindex file fetch error");
                break;
            }
        }

        return files;
    }

    private static string? GetString(Dictionary<string, object?> dict, string key)
    {
        if (!dict.TryGetValue(key, out var val) || val is null) return null;
        if (val is System.Text.Json.JsonElement je)
        {
            return je.ValueKind == System.Text.Json.JsonValueKind.Null ? null : je.ToString();
        }

        return val.ToString();
    }

    private static int GetInt(Dictionary<string, object?> dict, string key)
    {
        if (!dict.TryGetValue(key, out var val) || val is null) return 0;
        if (val is System.Text.Json.JsonElement je && je.ValueKind == System.Text.Json.JsonValueKind.Number)
            return je.GetInt32();
        if (val is int i) return i;
        if (int.TryParse(val.ToString(), out var parsed)) return parsed;
        return 0;
    }

    private static List<string> GetTags(Dictionary<string, object?> dict)
    {
        if (!dict.TryGetValue("tags", out var val) || val is null) return new List<string>();
        if (val is System.Text.Json.JsonElement je && je.ValueKind == System.Text.Json.JsonValueKind.Array)
            return je.EnumerateArray().Select(e => e.GetString() ?? string.Empty).ToList();
        if (val is List<string> list) return list;
        return new List<string>();
    }

    private static Dictionary<string, object?> GetNestedDict(Dictionary<string, object?> dict, string key)
    {
        if (!dict.TryGetValue(key, out var val) || val is null) return new Dictionary<string, object?>();
        if (val is System.Text.Json.JsonElement je && je.ValueKind == System.Text.Json.JsonValueKind.Object)
        {
            return je.EnumerateObject().ToDictionary(p => p.Name, p => (object?)p.Value);
        }

        if (val is Dictionary<string, object?> d) return d;
        return new Dictionary<string, object?>();
    }

    private static string GetJsonStr(System.Text.Json.JsonElement elem, string prop)
    {
        if (elem.TryGetProperty(prop, out var val))
            return val.GetString() ?? string.Empty;
        return string.Empty;
    }

    private static string? GetJsonStrOrNull(System.Text.Json.JsonElement elem, string prop)
    {
        if (elem.TryGetProperty(prop, out var val) && val.ValueKind != System.Text.Json.JsonValueKind.Null)
            return val.GetString();
        return null;
    }

    private static int? GetJsonInt(System.Text.Json.JsonElement elem, string prop)
    {
        if (elem.TryGetProperty(prop, out var val) && val.ValueKind == System.Text.Json.JsonValueKind.Number)
            return val.GetInt32();
        return null;
    }

    private static List<string> GetJsonStrArray(System.Text.Json.JsonElement elem, string prop)
    {
        if (elem.TryGetProperty(prop, out var val) && val.ValueKind == System.Text.Json.JsonValueKind.Array)
            return val.EnumerateArray().Select(e => e.GetString() ?? string.Empty).ToList();
        return new List<string>();
    }
}
