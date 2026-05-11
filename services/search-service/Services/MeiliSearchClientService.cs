using Meilisearch;
using Microsoft.Extensions.Options;
using OtterWorks.SearchService.Configuration;
using OtterWorks.SearchService.Models;
namespace OtterWorks.SearchService.Services;

public class MeiliSearchClientService : IMeiliSearchService
{
    private readonly MeilisearchClient _client;
    private readonly string _documentsIndexName;
    private readonly string _filesIndexName;
    private readonly ISearchAnalyticsTracker _analytics;
    private readonly Serilog.ILogger _logger = Serilog.Log.ForContext<MeiliSearchClientService>();

    public MeiliSearchClientService(IOptions<MeiliSearchSettings> settings, ISearchAnalyticsTracker analytics)
    {
        var config = settings.Value;
        _client = new MeilisearchClient(config.Url, string.IsNullOrEmpty(config.ApiKey) ? null : config.ApiKey);
        _documentsIndexName = config.DocumentsIndex;
        _filesIndexName = config.FilesIndex;
        _analytics = analytics;
    }

    internal MeiliSearchClientService(MeilisearchClient client, string documentsIndex, string filesIndex, ISearchAnalyticsTracker analytics)
    {
        _client = client;
        _documentsIndexName = documentsIndex;
        _filesIndexName = filesIndex;
        _analytics = analytics;
    }

    private static string Escape(string value) =>
        value.Replace("\\", "\\\\").Replace("\"", "\\\"");

    public async Task EnsureIndicesAsync()
    {
        foreach (var indexName in new[] { _documentsIndexName, _filesIndexName })
        {
            try
            {
                await _client.GetIndexAsync(indexName);
            }
            catch (MeilisearchApiError)
            {
                var task = await _client.CreateIndexAsync(indexName, "id");
                await _client.WaitForTaskAsync(task.TaskUid, timeoutMs: 30000);
                _logger.Information("MeiliSearch index created: {Index}", indexName);
            }
        }

        var docsIndex = _client.Index(_documentsIndexName);
        await docsIndex.UpdateSearchableAttributesAsync(new[] { "title", "content", "tags" });
        await docsIndex.UpdateFilterableAttributesAsync(new[] { "type", "owner_id", "tags", "created_at", "updated_at" });
        await docsIndex.UpdateSortableAttributesAsync(new[] { "updated_at", "created_at" });
        await docsIndex.UpdateRankingRulesAsync(new[] { "words", "typo", "proximity", "attribute", "sort", "exactness" });

        var filesIndex = _client.Index(_filesIndexName);
        await filesIndex.UpdateSearchableAttributesAsync(new[] { "name", "tags", "mime_type" });
        await filesIndex.UpdateFilterableAttributesAsync(new[] { "type", "owner_id", "mime_type", "folder_id", "tags", "created_at", "updated_at" });
        await filesIndex.UpdateSortableAttributesAsync(new[] { "updated_at", "created_at", "size" });
        await filesIndex.UpdateRankingRulesAsync(new[] { "words", "typo", "proximity", "attribute", "sort", "exactness" });

        _logger.Information("MeiliSearch indices configured");
    }

    public bool Ping()
    {
        try
        {
            _client.HealthAsync().GetAwaiter().GetResult();
            return true;
        }
        catch
        {
            return false;
        }
    }

    private List<string> ResolveIndices(string? docType)
    {
        if (docType == "document") return new List<string> { _documentsIndexName };
        if (docType == "file") return new List<string> { _filesIndexName };
        return new List<string> { _documentsIndexName, _filesIndexName };
    }

    private static SearchQuery BuildSearchParams(int page, int pageSize, List<string> filterParts, bool multiIndex)
    {
        int fetchLimit;
        int offset;

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

        var searchParams = new SearchQuery
        {
            Offset = offset,
            Limit = fetchLimit,
            AttributesToHighlight = new[] { "title", "name", "content" },
            HighlightPreTag = "<em>",
            HighlightPostTag = "</em>",
            AttributesToCrop = new[] { "content" },
            CropLength = 200,
        };

        if (filterParts.Count > 0)
        {
            searchParams.Filter = string.Join(" AND ", filterParts);
        }

        return searchParams;
    }

    private SearchHit ParseHit(Dictionary<string, object?> hit, string indexName)
    {
        bool isDoc = indexName == _documentsIndexName;
        var formatted = new Dictionary<string, object?>();
        if (hit.TryGetValue("_formatted", out var fmtObj) && fmtObj is System.Text.Json.JsonElement fmtElement)
        {
            foreach (var prop in fmtElement.EnumerateObject())
            {
                formatted[prop.Name] = prop.Value.ToString();
            }
        }

        var highlights = new Dictionary<string, List<string>>();
        foreach (var field in new[] { "title", "name", "content" })
        {
            if (formatted.TryGetValue(field, out var val) && val is string s && s.Contains("<em>"))
            {
                highlights[field] = new List<string> { s };
            }
        }

        string GetStr(string key, string def = "") =>
            hit.TryGetValue(key, out var v) && v is not null ? v.ToString() ?? def : def;

        List<string> GetTags()
        {
            if (!hit.TryGetValue("tags", out var v) || v is null) return new List<string>();
            if (v is System.Text.Json.JsonElement je && je.ValueKind == System.Text.Json.JsonValueKind.Array)
            {
                return je.EnumerateArray().Select(e => e.ToString()).ToList();
            }

            return new List<string>();
        }

        int? GetIntOrNull(string key)
        {
            if (!hit.TryGetValue(key, out var v) || v is null) return null;
            if (v is System.Text.Json.JsonElement je)
            {
                if (je.ValueKind == System.Text.Json.JsonValueKind.Number) return je.GetInt32();
                return null;
            }

            if (v is int i) return i;
            if (int.TryParse(v.ToString(), out var parsed)) return parsed;
            return null;
        }

        string? GetStrOrNull(string key) =>
            hit.TryGetValue(key, out var v) && v is not null ? v.ToString() : null;

        string contentSnippet = string.Empty;
        if (isDoc && formatted.TryGetValue("content", out var contentVal) && contentVal is string cs)
        {
            contentSnippet = cs.Length > 200 ? cs[..200] : cs;
        }

        string typeVal = GetStr("type", isDoc ? "document" : "file");

        return new SearchHit
        {
            Id = GetStr("id"),
            Title = isDoc ? GetStr("title") : GetStr("name"),
            ContentSnippet = contentSnippet,
            Type = typeVal,
            OwnerId = GetStr("owner_id"),
            Tags = GetTags(),
            Score = 0.0,
            Highlights = highlights,
            CreatedAt = GetStrOrNull("created_at"),
            UpdatedAt = GetStrOrNull("updated_at"),
            MimeType = GetStrOrNull("mime_type"),
            FolderId = GetStrOrNull("folder_id"),
            Size = GetIntOrNull("size"),
        };
    }

    public SearchResponse Search(string query, string? docType = null, string? ownerId = null, int page = 1, int pageSize = 20)
    {
        var filterParts = new List<string>();
        if (!string.IsNullOrEmpty(docType))
            filterParts.Add($"type = \"{Escape(docType)}\"");
        if (!string.IsNullOrEmpty(ownerId))
            filterParts.Add($"owner_id = \"{Escape(ownerId)}\"");

        var indicesToSearch = ResolveIndices(docType);
        bool multiIndex = indicesToSearch.Count > 1;
        var searchParams = BuildSearchParams(page, pageSize, filterParts, multiIndex);

        var allHits = new List<SearchHit>();
        int total = 0;

        foreach (var indexName in indicesToSearch)
        {
            var index = _client.Index(indexName);
            ISearchable<Dictionary<string, object?>> result;
            try
            {
                result = index.SearchAsync<Dictionary<string, object?>>(query, searchParams).GetAwaiter().GetResult();
            }
            catch (MeilisearchApiError exc)
            {
                _logger.Warning("Search filter error on {Index}: {Error}", indexName, exc.Message);
                throw new ArgumentException($"Invalid search filter: {exc.Message}", exc);
            }

            if (result is Meilisearch.SearchResult<Dictionary<string, object?>> sr)
                total += sr.EstimatedTotalHits;
            else if (result is Meilisearch.PaginatedSearchResult<Dictionary<string, object?>> pr)
                total += pr.TotalHits;
            foreach (var hit in result.Hits)
            {
                allHits.Add(ParseHit(hit, indexName));
            }
        }

        _analytics.Record(query, total);

        int start = multiIndex ? (page - 1) * pageSize : 0;
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

    public SearchResponse AdvancedSearch(string? query = null, string? docType = null, string? ownerId = null, List<string>? tags = null, string? dateFrom = null, string? dateTo = null, int page = 1, int pageSize = 20)
    {
        var filterParts = new List<string>();
        if (!string.IsNullOrEmpty(docType))
            filterParts.Add($"type = \"{Escape(docType)}\"");
        if (!string.IsNullOrEmpty(ownerId))
            filterParts.Add($"owner_id = \"{Escape(ownerId)}\"");
        if (tags is { Count: > 0 })
        {
            var tagFilters = tags.Select(t => $"tags = \"{Escape(t)}\"");
            filterParts.Add($"({string.Join(" OR ", tagFilters)})");
        }

        if (!string.IsNullOrEmpty(dateFrom))
            filterParts.Add($"created_at >= \"{Escape(dateFrom)}\"");
        if (!string.IsNullOrEmpty(dateTo))
            filterParts.Add($"created_at <= \"{Escape(dateTo)}\"");

        string searchTerm = query ?? string.Empty;
        var indicesToSearch = ResolveIndices(docType);
        bool multiIndex = indicesToSearch.Count > 1;
        var searchParams = BuildSearchParams(page, pageSize, filterParts, multiIndex);

        var allHits = new List<SearchHit>();
        int total = 0;

        foreach (var indexName in indicesToSearch)
        {
            var index = _client.Index(indexName);
            var result = index.SearchAsync<Dictionary<string, object?>>(searchTerm, searchParams).GetAwaiter().GetResult();
            if (result is Meilisearch.SearchResult<Dictionary<string, object?>> srAdv)
                total += srAdv.EstimatedTotalHits;
            else if (result is Meilisearch.PaginatedSearchResult<Dictionary<string, object?>> prAdv)
                total += prAdv.TotalHits;
            foreach (var hit in result.Hits)
            {
                allHits.Add(ParseHit(hit, indexName));
            }
        }

        string recordQuery = string.IsNullOrEmpty(searchTerm) ? "*" : searchTerm;
        _analytics.Record(recordQuery, total);

        int start = multiIndex ? (page - 1) * pageSize : 0;
        var pageHits = allHits.Skip(start).Take(pageSize).ToList();

        return new SearchResponse
        {
            Results = pageHits,
            Total = total,
            Page = page,
            PageSize = pageSize,
            Query = recordQuery,
        };
    }

    public List<string> Suggest(string prefix, int size = 10)
    {
        var suggestions = new List<string>();
        var seen = new HashSet<string>();

        foreach (var indexName in new[] { _documentsIndexName, _filesIndexName })
        {
            var index = _client.Index(indexName);
            var searchParams = new SearchQuery
            {
                Limit = size,
                AttributesToRetrieve = new[] { "title", "name" },
            };
            var result = index.SearchAsync<Dictionary<string, object?>>(prefix, searchParams).GetAwaiter().GetResult();
            foreach (var hit in result.Hits)
            {
                string? text = null;
                if (hit.TryGetValue("title", out var titleVal) && titleVal is not null)
                    text = titleVal.ToString();
                if (string.IsNullOrEmpty(text) && hit.TryGetValue("name", out var nameVal) && nameVal is not null)
                    text = nameVal.ToString();

                if (!string.IsNullOrEmpty(text) && seen.Add(text))
                {
                    suggestions.Add(text);
                    if (suggestions.Count >= size) break;
                }
            }

            if (suggestions.Count >= size) break;
        }

        return suggestions;
    }

    private void WaitAndCheck(int taskUid, int timeoutMs = 10000)
    {
        var result = _client.WaitForTaskAsync(taskUid, timeoutMs: timeoutMs).GetAwaiter().GetResult();
        if (result.Status != Meilisearch.TaskInfoStatus.Succeeded)
        {
            throw new InvalidOperationException(
                $"MeiliSearch task {taskUid} {result.Status}: {(result.Error != null ? string.Join(", ", result.Error.Select(kv => $"{kv.Key}={kv.Value}")) : "unknown")}");
        }
    }

    public void IndexDocument(Dictionary<string, object?> document)
    {
        var doc = new Dictionary<string, object?>(document) { ["type"] = "document" };
        var index = _client.Index(_documentsIndexName);
        var task = index.AddDocumentsAsync(new[] { doc }).GetAwaiter().GetResult();
        WaitAndCheck(task.TaskUid);
        _logger.Information("Document indexed: {DocumentId}", doc.GetValueOrDefault("id"));
    }

    public void IndexFile(Dictionary<string, object?> fileData)
    {
        var doc = new Dictionary<string, object?>(fileData) { ["type"] = "file" };
        var index = _client.Index(_filesIndexName);
        var task = index.AddDocumentsAsync(new[] { doc }).GetAwaiter().GetResult();
        try
        {
            WaitAndCheck(task.TaskUid);
        }
        catch (InvalidOperationException exc) when (exc.Message.Contains("MDB_KEYEXIST"))
        {
            _logger.Warning("LMDB key exists retry for file {FileId}", doc.GetValueOrDefault("id"));
            var delTask = index.DeleteOneDocumentAsync(doc["id"]?.ToString() ?? string.Empty).GetAwaiter().GetResult();
            WaitAndCheck(delTask.TaskUid);
            var retryTask = index.AddDocumentsAsync(new[] { doc }).GetAwaiter().GetResult();
            WaitAndCheck(retryTask.TaskUid);
        }

        _logger.Information("File indexed: {FileId}", doc.GetValueOrDefault("id"));
    }

    public bool DeleteDocument(string docType, string docId)
    {
        string indexName = docType == "document" ? _documentsIndexName : _filesIndexName;
        var index = _client.Index(indexName);
        try
        {
            index.GetDocumentAsync<Dictionary<string, object?>>(docId).GetAwaiter().GetResult();
        }
        catch (MeilisearchApiError)
        {
            _logger.Warning("Document not found in index: {DocId} in {Index}", docId, indexName);
            return false;
        }

        var task = index.DeleteOneDocumentAsync(docId).GetAwaiter().GetResult();
        WaitAndCheck(task.TaskUid);
        _logger.Information("Document removed from index: {DocId} in {Index}", docId, indexName);
        return true;
    }

    public Dictionary<string, object?> Reindex(List<Dictionary<string, object?>>? documents = null, List<Dictionary<string, object?>>? files = null)
    {
        foreach (var indexName in new[] { _documentsIndexName, _filesIndexName })
        {
            try
            {
                var task = _client.DeleteIndexAsync(indexName).GetAwaiter().GetResult();
                WaitAndCheck(task.TaskUid, 30000);
                _logger.Information("MeiliSearch index deleted: {Index}", indexName);
            }
            catch
            {
                // Ignore if index doesn't exist
            }
        }

        EnsureIndicesAsync().GetAwaiter().GetResult();

        var indexedCounts = new Dictionary<string, int> { ["documents"] = 0, ["files"] = 0 };

        if (documents is { Count: > 0 })
        {
            var idx = _client.Index(_documentsIndexName);
            for (int i = 0; i < documents.Count; i += 500)
            {
                var batch = documents.Skip(i).Take(500).ToArray();
                var task = idx.AddDocumentsAsync(batch).GetAwaiter().GetResult();
                WaitAndCheck(task.TaskUid, 60000);
            }

            indexedCounts["documents"] = documents.Count;
        }

        if (files is { Count: > 0 })
        {
            var idx = _client.Index(_filesIndexName);
            for (int i = 0; i < files.Count; i += 500)
            {
                var batch = files.Skip(i).Take(500).ToArray();
                var task = idx.AddDocumentsAsync(batch).GetAwaiter().GetResult();
                WaitAndCheck(task.TaskUid, 60000);
            }

            indexedCounts["files"] = files.Count;
        }

        return new Dictionary<string, object?>
        {
            ["status"] = "reindexed",
            ["indices"] = new[] { _documentsIndexName, _filesIndexName },
            ["indexed_counts"] = indexedCounts,
        };
    }
}
