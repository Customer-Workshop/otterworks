using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Options;
using OtterWorks.SearchService.Config;
using OtterWorks.SearchService.Models;

namespace OtterWorks.SearchService.Services;

public class MeilisearchService : IMeilisearchService
{
    private readonly HttpClient _httpClient;
    private readonly MeilisearchSettings _settings;
    private readonly ILogger<MeilisearchService> _logger;
    private readonly SearchAnalyticsStore _analytics;

    public MeilisearchService(
        HttpClient httpClient,
        IOptions<MeilisearchSettings> settings,
        ILogger<MeilisearchService> logger,
        SearchAnalyticsStore analytics)
    {
        _httpClient = httpClient;
        _settings = settings.Value;
        _logger = logger;
        _analytics = analytics;
    }

    private static string Escape(string value) =>
        value.Replace("\\", "\\\\").Replace("\"", "\\\"");

    public async Task EnsureIndicesAsync(CancellationToken ct = default)
    {
        foreach (var indexName in new[] { _settings.DocumentsIndex, _settings.FilesIndex })
        {
            try
            {
                var response = await _httpClient.GetAsync($"/indexes/{indexName}", ct);
                if (!response.IsSuccessStatusCode)
                {
                    var createBody = JsonSerializer.Serialize(new { uid = indexName, primaryKey = "id" });
                    var createResponse = await _httpClient.PostAsync(
                        "/indexes",
                        new StringContent(createBody, Encoding.UTF8, "application/json"),
                        ct);
                    if (createResponse.IsSuccessStatusCode)
                    {
                        var taskInfo = await JsonSerializer.DeserializeAsync<JsonElement>(
                            await createResponse.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
                        if (taskInfo.TryGetProperty("taskUid", out var taskUid))
                        {
                            await WaitForTaskAsync(taskUid.GetInt64(), 30000, ct);
                        }
                    }

                    _logger.LogInformation("Meilisearch index created: {Index}", indexName);
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to check/create Meilisearch index {Index}", indexName);
            }
        }

        await ConfigureIndexAsync(_settings.DocumentsIndex, ["title", "content", "tags"], ["type", "owner_id", "tags", "created_at", "updated_at"], ["updated_at", "created_at"], ct);
        await ConfigureIndexAsync(_settings.FilesIndex, ["name", "tags", "mime_type"], ["type", "owner_id", "mime_type", "folder_id", "tags", "created_at", "updated_at"], ["updated_at", "created_at", "size"], ct);

        _logger.LogInformation("Meilisearch indices configured");
    }

    private async Task ConfigureIndexAsync(string indexName, string[] searchable, string[] filterable, string[] sortable, CancellationToken ct)
    {
        try
        {
            var settingsBody = JsonSerializer.Serialize(new
            {
                searchableAttributes = searchable,
                filterableAttributes = filterable,
                sortableAttributes = sortable,
                rankingRules = new[] { "words", "typo", "proximity", "attribute", "sort", "exactness" },
            });
            await _httpClient.PatchAsync(
                $"/indexes/{indexName}/settings",
                new StringContent(settingsBody, Encoding.UTF8, "application/json"),
                ct);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to configure index {Index}", indexName);
        }
    }

    public async Task<bool> PingAsync(CancellationToken ct = default)
    {
        try
        {
            var response = await _httpClient.GetAsync("/health", ct);
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    public async Task<SearchResponse> SearchAsync(
        string query,
        string? docType = null,
        string? ownerId = null,
        int page = 1,
        int pageSize = 20,
        CancellationToken ct = default)
    {
        var filterParts = new List<string>();
        if (!string.IsNullOrEmpty(docType))
        {
            filterParts.Add($"type = \"{Escape(docType)}\"");
        }

        if (!string.IsNullOrEmpty(ownerId))
        {
            filterParts.Add($"owner_id = \"{Escape(ownerId)}\"");
        }

        var indicesToSearch = ResolveIndices(docType);
        var multiIndex = indicesToSearch.Count > 1;
        var searchParams = BuildSearchParams(page, pageSize, filterParts, multiIndex);

        var allHits = new List<SearchHit>();
        var total = 0;

        foreach (var indexName in indicesToSearch)
        {
            var (hits, estimatedTotal) = await ExecuteSearchAsync(indexName, query, searchParams, ct);
            total += estimatedTotal;
            allHits.AddRange(hits);
        }

        RecordAnalytics(query, total);

        var start = multiIndex ? (page - 1) * pageSize : 0;
        var pageHits = allHits.Skip(start).Take(pageSize).ToList();

        return new SearchResponse
        {
            Results = pageHits,
            Total = total,
            Page = page,
            PageSize = pageSize,
            Query = query,
        };
    }

    public async Task<SearchResponse> AdvancedSearchAsync(
        string? query = null,
        string? docType = null,
        string? ownerId = null,
        List<string>? tags = null,
        string? dateFrom = null,
        string? dateTo = null,
        int page = 1,
        int pageSize = 20,
        CancellationToken ct = default)
    {
        var filterParts = new List<string>();
        if (!string.IsNullOrEmpty(docType))
        {
            filterParts.Add($"type = \"{Escape(docType)}\"");
        }

        if (!string.IsNullOrEmpty(ownerId))
        {
            filterParts.Add($"owner_id = \"{Escape(ownerId)}\"");
        }

        if (tags is { Count: > 0 })
        {
            var tagFilters = tags.Select(t => $"tags = \"{Escape(t)}\"");
            filterParts.Add($"({string.Join(" OR ", tagFilters)})");
        }

        if (!string.IsNullOrEmpty(dateFrom))
        {
            filterParts.Add($"created_at >= \"{Escape(dateFrom)}\"");
        }

        if (!string.IsNullOrEmpty(dateTo))
        {
            filterParts.Add($"created_at <= \"{Escape(dateTo)}\"");
        }

        var searchTerm = query ?? string.Empty;
        var indicesToSearch = ResolveIndices(docType);
        var multiIndex = indicesToSearch.Count > 1;
        var searchParams = BuildSearchParams(page, pageSize, filterParts, multiIndex);

        var allHits = new List<SearchHit>();
        var total = 0;

        foreach (var indexName in indicesToSearch)
        {
            var (hits, estimatedTotal) = await ExecuteSearchAsync(indexName, searchTerm, searchParams, ct);
            total += estimatedTotal;
            allHits.AddRange(hits);
        }

        var analyticsQuery = string.IsNullOrEmpty(searchTerm) ? "*" : searchTerm;
        RecordAnalytics(analyticsQuery, total);

        var start = multiIndex ? (page - 1) * pageSize : 0;
        var pageHits = allHits.Skip(start).Take(pageSize).ToList();

        return new SearchResponse
        {
            Results = pageHits,
            Total = total,
            Page = page,
            PageSize = pageSize,
            Query = analyticsQuery,
        };
    }

    public async Task<List<string>> SuggestAsync(string prefix, int size = 10, CancellationToken ct = default)
    {
        var suggestions = new List<string>();
        var seen = new HashSet<string>();

        foreach (var indexName in new[] { _settings.DocumentsIndex, _settings.FilesIndex })
        {
            var body = JsonSerializer.Serialize(new
            {
                q = prefix,
                limit = size,
                attributesToRetrieve = new[] { "title", "name" },
            });

            try
            {
                var response = await _httpClient.PostAsync(
                    $"/indexes/{indexName}/search",
                    new StringContent(body, Encoding.UTF8, "application/json"),
                    ct);

                if (!response.IsSuccessStatusCode)
                {
                    continue;
                }

                var result = await JsonSerializer.DeserializeAsync<JsonElement>(
                    await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);

                if (result.TryGetProperty("hits", out var hits))
                {
                    foreach (var hit in hits.EnumerateArray())
                    {
                        var text = hit.TryGetProperty("title", out var title) && title.ValueKind == JsonValueKind.String
                            ? title.GetString()
                            : (hit.TryGetProperty("name", out var name) && name.ValueKind == JsonValueKind.String ? name.GetString() : null);

                        if (!string.IsNullOrEmpty(text) && seen.Add(text))
                        {
                            suggestions.Add(text);
                            if (suggestions.Count >= size)
                            {
                                break;
                            }
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Suggest failed for index {Index}", indexName);
            }

            if (suggestions.Count >= size)
            {
                break;
            }
        }

        return suggestions;
    }

    public async Task IndexDocumentAsync(Dictionary<string, object?> document, CancellationToken ct = default)
    {
        document["type"] = "document";
        var index = _settings.DocumentsIndex;
        var body = JsonSerializer.Serialize(new[] { document });
        var response = await _httpClient.PostAsync(
            $"/indexes/{index}/documents",
            new StringContent(body, Encoding.UTF8, "application/json"),
            ct);
        response.EnsureSuccessStatusCode();

        var taskInfo = await JsonSerializer.DeserializeAsync<JsonElement>(
            await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
        if (taskInfo.TryGetProperty("taskUid", out var taskUid))
        {
            await WaitForTaskAsync(taskUid.GetInt64(), 10000, ct);
        }

        _logger.LogInformation("Document indexed: {DocumentId}", document.GetValueOrDefault("id"));
    }

    public async Task IndexFileAsync(Dictionary<string, object?> fileData, CancellationToken ct = default)
    {
        fileData["type"] = "file";
        var index = _settings.FilesIndex;
        var body = JsonSerializer.Serialize(new[] { fileData });
        var response = await _httpClient.PostAsync(
            $"/indexes/{index}/documents",
            new StringContent(body, Encoding.UTF8, "application/json"),
            ct);
        response.EnsureSuccessStatusCode();

        var taskInfo = await JsonSerializer.DeserializeAsync<JsonElement>(
            await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
        if (taskInfo.TryGetProperty("taskUid", out var taskUid))
        {
            try
            {
                await WaitForTaskAsync(taskUid.GetInt64(), 10000, ct);
            }
            catch (InvalidOperationException ex) when (ex.Message.Contains("MDB_KEYEXIST", StringComparison.Ordinal))
            {
                _logger.LogWarning("LMDB key exists retry for file {FileId}", fileData.GetValueOrDefault("id"));
                var deleteResponse = await _httpClient.DeleteAsync($"/indexes/{index}/documents/{fileData["id"]}", ct);
                if (deleteResponse.IsSuccessStatusCode)
                {
                    var delTask = await JsonSerializer.DeserializeAsync<JsonElement>(
                        await deleteResponse.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
                    if (delTask.TryGetProperty("taskUid", out var delUid))
                    {
                        await WaitForTaskAsync(delUid.GetInt64(), 10000, ct);
                    }
                }

                var retryResponse = await _httpClient.PostAsync(
                    $"/indexes/{index}/documents",
                    new StringContent(body, Encoding.UTF8, "application/json"),
                    ct);
                retryResponse.EnsureSuccessStatusCode();

                var retryTask = await JsonSerializer.DeserializeAsync<JsonElement>(
                    await retryResponse.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
                if (retryTask.TryGetProperty("taskUid", out var retryUid))
                {
                    await WaitForTaskAsync(retryUid.GetInt64(), 10000, ct);
                }
            }
        }

        _logger.LogInformation("File indexed: {FileId}", fileData.GetValueOrDefault("id"));
    }

    public async Task<bool> DeleteDocumentAsync(string docType, string docId, CancellationToken ct = default)
    {
        var indexName = docType == "document" ? _settings.DocumentsIndex : _settings.FilesIndex;

        var getResponse = await _httpClient.GetAsync($"/indexes/{indexName}/documents/{docId}", ct);
        if (!getResponse.IsSuccessStatusCode)
        {
            _logger.LogWarning("Document not found in index: {DocId} in {Index}", docId, indexName);
            return false;
        }

        var deleteResponse = await _httpClient.DeleteAsync($"/indexes/{indexName}/documents/{docId}", ct);
        if (deleteResponse.IsSuccessStatusCode)
        {
            var taskInfo = await JsonSerializer.DeserializeAsync<JsonElement>(
                await deleteResponse.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            if (taskInfo.TryGetProperty("taskUid", out var taskUid))
            {
                await WaitForTaskAsync(taskUid.GetInt64(), 10000, ct);
            }
        }

        _logger.LogInformation("Document removed from index: {DocId} in {Index}", docId, indexName);
        return true;
    }

    public async Task<ReindexResult> ReindexAsync(
        List<Dictionary<string, object?>>? documents = null,
        List<Dictionary<string, object?>>? files = null,
        CancellationToken ct = default)
    {
        foreach (var indexName in new[] { _settings.DocumentsIndex, _settings.FilesIndex })
        {
            try
            {
                var delResponse = await _httpClient.DeleteAsync($"/indexes/{indexName}", ct);
                if (delResponse.IsSuccessStatusCode)
                {
                    var taskInfo = await JsonSerializer.DeserializeAsync<JsonElement>(
                        await delResponse.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
                    if (taskInfo.TryGetProperty("taskUid", out var taskUid))
                    {
                        await WaitForTaskAsync(taskUid.GetInt64(), 30000, ct);
                    }
                }
            }
            catch
            {
                // Ignore errors during deletion
            }
        }

        await EnsureIndicesAsync(ct);

        var indexedCounts = new Dictionary<string, int> { ["documents"] = 0, ["files"] = 0 };

        if (documents is { Count: > 0 })
        {
            await BulkIndexAsync(_settings.DocumentsIndex, documents, ct);
            indexedCounts["documents"] = documents.Count;
        }

        if (files is { Count: > 0 })
        {
            await BulkIndexAsync(_settings.FilesIndex, files, ct);
            indexedCounts["files"] = files.Count;
        }

        return new ReindexResult
        {
            Status = "reindexed",
            Indices = [_settings.DocumentsIndex, _settings.FilesIndex],
            IndexedCounts = indexedCounts,
        };
    }

    public AnalyticsData GetAnalytics() => _analytics.GetAnalytics();

    private static Dictionary<string, object?> BuildSearchParams(int page, int pageSize, List<string> filterParts, bool multiIndex)
    {
        int offset;
        int fetchLimit;

        if (multiIndex)
        {
            fetchLimit = page * pageSize;
            offset = 0;
        }
        else
        {
            fetchLimit = pageSize;
            offset = (page - 1) * pageSize;
        }

        var p = new Dictionary<string, object?>
        {
            ["offset"] = offset,
            ["limit"] = fetchLimit,
            ["attributesToHighlight"] = new[] { "title", "name", "content" },
            ["highlightPreTag"] = "<em>",
            ["highlightPostTag"] = "</em>",
            ["attributesToCrop"] = new[] { "content" },
            ["cropLength"] = 200,
        };

        if (filterParts.Count > 0)
        {
            p["filter"] = string.Join(" AND ", filterParts);
        }

        return p;
    }

    private async Task<(List<SearchHit> Hits, int EstimatedTotal)> ExecuteSearchAsync(
        string indexName, string query, Dictionary<string, object?> searchParams, CancellationToken ct)
    {
        var requestBody = new Dictionary<string, object?>(searchParams) { ["q"] = query };
        var body = JsonSerializer.Serialize(requestBody);

        var response = await _httpClient.PostAsync(
            $"/indexes/{indexName}/search",
            new StringContent(body, Encoding.UTF8, "application/json"),
            ct);

        if (!response.IsSuccessStatusCode)
        {
            var errorContent = await response.Content.ReadAsStringAsync(ct);
            _logger.LogWarning("Search filter error on {Index}: {Error}", indexName, errorContent);
            throw new ArgumentException($"Invalid search filter: {errorContent}");
        }

        var result = await JsonSerializer.DeserializeAsync<JsonElement>(
            await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);

        var estimatedTotal = result.TryGetProperty("estimatedTotalHits", out var totalProp) ? totalProp.GetInt32() : 0;
        var hits = new List<SearchHit>();

        if (result.TryGetProperty("hits", out var hitsArray))
        {
            foreach (var hit in hitsArray.EnumerateArray())
            {
                hits.Add(ParseHit(hit, indexName));
            }
        }

        return (hits, estimatedTotal);
    }

    private SearchHit ParseHit(JsonElement hit, string indexName)
    {
        var formatted = hit.TryGetProperty("_formatted", out var fmt) ? fmt : default;
        var highlights = new Dictionary<string, List<string>>();

        foreach (var field in new[] { "title", "name", "content" })
        {
            if (formatted.ValueKind == JsonValueKind.Object &&
                formatted.TryGetProperty(field, out var val) &&
                val.ValueKind == JsonValueKind.String &&
                val.GetString()?.Contains("<em>", StringComparison.Ordinal) == true)
            {
                highlights[field] = [val.GetString()!];
            }
        }

        var isDoc = indexName == _settings.DocumentsIndex;
        var contentSnippet = string.Empty;
        if (isDoc && formatted.ValueKind == JsonValueKind.Object &&
            formatted.TryGetProperty("content", out var contentVal) &&
            contentVal.ValueKind == JsonValueKind.String)
        {
            var raw = contentVal.GetString() ?? string.Empty;
            contentSnippet = raw.Length > 200 ? raw[..200] : raw;
        }

        return new SearchHit
        {
            Id = hit.TryGetProperty("id", out var id) && id.ValueKind == JsonValueKind.String ? id.GetString() ?? string.Empty : string.Empty,
            Title = isDoc
                ? (hit.TryGetProperty("title", out var t) && t.ValueKind == JsonValueKind.String ? t.GetString() ?? string.Empty : string.Empty)
                : (hit.TryGetProperty("name", out var n) && n.ValueKind == JsonValueKind.String ? n.GetString() ?? string.Empty : string.Empty),
            ContentSnippet = contentSnippet,
            Type = hit.TryGetProperty("type", out var tp) && tp.ValueKind == JsonValueKind.String
                ? tp.GetString() ?? (isDoc ? "document" : "file")
                : (isDoc ? "document" : "file"),
            OwnerId = hit.TryGetProperty("owner_id", out var oid) && oid.ValueKind == JsonValueKind.String ? oid.GetString() ?? string.Empty : string.Empty,
            Tags = hit.TryGetProperty("tags", out var tags) && tags.ValueKind == JsonValueKind.Array
                ? tags.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!).ToList()
                : [],
            Score = 0.0,
            Highlights = highlights,
            CreatedAt = hit.TryGetProperty("created_at", out var ca) && ca.ValueKind == JsonValueKind.String ? ca.GetString() : null,
            UpdatedAt = hit.TryGetProperty("updated_at", out var ua) && ua.ValueKind == JsonValueKind.String ? ua.GetString() : null,
            MimeType = hit.TryGetProperty("mime_type", out var mt) && mt.ValueKind == JsonValueKind.String ? mt.GetString() : null,
            FolderId = hit.TryGetProperty("folder_id", out var fi) && fi.ValueKind == JsonValueKind.String ? fi.GetString() : null,
            Size = hit.TryGetProperty("size", out var sz) && sz.ValueKind == JsonValueKind.Number ? sz.GetInt32() : null,
        };
    }

    private List<string> ResolveIndices(string? docType) => docType switch
    {
        "document" => [_settings.DocumentsIndex],
        "file" => [_settings.FilesIndex],
        _ => [_settings.DocumentsIndex, _settings.FilesIndex],
    };

    private void RecordAnalytics(string query, int resultCount) => _analytics.Record(query, resultCount);

    private async Task WaitForTaskAsync(long taskUid, int timeoutMs, CancellationToken ct)
    {
        var deadline = DateTime.UtcNow.AddMilliseconds(timeoutMs);
        while (DateTime.UtcNow < deadline)
        {
            var response = await _httpClient.GetAsync($"/tasks/{taskUid}", ct);
            if (response.IsSuccessStatusCode)
            {
                var task = await JsonSerializer.DeserializeAsync<JsonElement>(
                    await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
                if (task.TryGetProperty("status", out var status))
                {
                    var statusStr = status.GetString();
                    if (statusStr == "succeeded")
                    {
                        return;
                    }

                    if (statusStr == "failed")
                    {
                        var error = task.TryGetProperty("error", out var err) ? err.ToString() : "unknown";
                        throw new InvalidOperationException($"Meilisearch task {taskUid} failed: {error}");
                    }
                }
            }

            await Task.Delay(100, ct);
        }
    }

    private async Task BulkIndexAsync(string indexName, List<Dictionary<string, object?>> items, CancellationToken ct)
    {
        const int batchSize = 500;
        for (var i = 0; i < items.Count; i += batchSize)
        {
            var batch = items.Skip(i).Take(batchSize).ToList();
            var body = JsonSerializer.Serialize(batch);
            var response = await _httpClient.PostAsync(
                $"/indexes/{indexName}/documents",
                new StringContent(body, Encoding.UTF8, "application/json"),
                ct);

            if (response.IsSuccessStatusCode)
            {
                var taskInfo = await JsonSerializer.DeserializeAsync<JsonElement>(
                    await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
                if (taskInfo.TryGetProperty("taskUid", out var taskUid))
                {
                    await WaitForTaskAsync(taskUid.GetInt64(), 60000, ct);
                }
            }
        }
    }
}
