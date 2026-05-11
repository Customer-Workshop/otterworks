using System.Text.Json;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Options;
using OtterWorks.ReportService.Configuration;
using OtterWorks.ReportService.Utilities;

namespace OtterWorks.ReportService.Services;

public class ReportDataFetcher : IReportDataFetcher
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly IMemoryCache _cache;
    private readonly ReportSettings _settings;
    private readonly ILogger<ReportDataFetcher> _logger;
    private static readonly MemoryCacheEntryOptions CacheOptions = new MemoryCacheEntryOptions()
        .SetSlidingExpiration(TimeSpan.FromMinutes(5));

    public ReportDataFetcher(
        IHttpClientFactory httpClientFactory,
        IMemoryCache cache,
        IOptions<ReportSettings> settings,
        ILogger<ReportDataFetcher> logger)
    {
        _httpClientFactory = httpClientFactory;
        _cache = cache;
        _settings = settings.Value;
        _logger = logger;
    }

    public async Task<List<Dictionary<string, object>>> FetchAnalyticsDataAsync(
        DateTime dateFrom,
        DateTime dateTo,
        Dictionary<string, string>? parameters)
    {
        string? metric = parameters?.GetValueOrDefault("metric");
        string cacheKey = $"analytics:{ReportDateUtils.ToIsoString(dateFrom)}:{ReportDateUtils.ToIsoString(dateTo)}"
            + (metric != null ? $":metric={metric}" : string.Empty);

        if (_cache.TryGetValue(cacheKey, out List<Dictionary<string, object>>? cached) && cached != null)
        {
            return cached;
        }

        try
        {
            string url = $"{_settings.AnalyticsServiceUrl}/api/v1/analytics/events"
                + $"?from={ReportDateUtils.ToIsoString(dateFrom)}"
                + $"&to={ReportDateUtils.ToIsoString(dateTo)}";

            if (!string.IsNullOrWhiteSpace(metric))
            {
                url += $"&metric={metric}";
            }

            _logger.LogInformation("Fetching analytics data from: {Url}", url);

            var client = _httpClientFactory.CreateClient("analytics");
            var response = await client.GetAsync(url);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadFromJsonAsync<JsonElement>();
            if (json.TryGetProperty("events", out var events))
            {
                var result = DeserializeDataList(events);
                _cache.Set(cacheKey, result, CacheOptions);
                return result;
            }

            return [];
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to fetch analytics data, using sample data");
            return GenerateSampleAnalyticsData(dateFrom, dateTo);
        }
    }

    public async Task<List<Dictionary<string, object>>> FetchAuditDataAsync(
        DateTime dateFrom,
        DateTime dateTo,
        Dictionary<string, string>? parameters)
    {
        string cacheKey = $"audit:{ReportDateUtils.ToIsoString(dateFrom)}:{ReportDateUtils.ToIsoString(dateTo)}";

        if (_cache.TryGetValue(cacheKey, out List<Dictionary<string, object>>? cached) && cached != null)
        {
            return cached;
        }

        try
        {
            string url = $"{_settings.AuditServiceUrl}/api/v1/audit/events"
                + $"?from={ReportDateUtils.ToIsoString(dateFrom)}"
                + $"&to={ReportDateUtils.ToIsoString(dateTo)}";

            _logger.LogInformation("Fetching audit data from: {Url}", url);

            var client = _httpClientFactory.CreateClient("audit");
            var response = await client.GetAsync(url);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadFromJsonAsync<JsonElement>();
            if (json.TryGetProperty("events", out var events))
            {
                var result = DeserializeDataList(events);
                _cache.Set(cacheKey, result, CacheOptions);
                return result;
            }

            return [];
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to fetch audit data, using sample data");
            return GenerateSampleAuditData(dateFrom, dateTo);
        }
    }

    public async Task<List<Dictionary<string, object>>> FetchUserActivityDataAsync(
        DateTime dateFrom,
        DateTime dateTo,
        Dictionary<string, string>? parameters)
    {
        try
        {
            string url = $"{_settings.AuthServiceUrl}/api/v1/users/activity"
                + $"?from={ReportDateUtils.ToIsoString(dateFrom)}"
                + $"&to={ReportDateUtils.ToIsoString(dateTo)}";

            _logger.LogInformation("Fetching user activity from: {Url}", url);

            var client = _httpClientFactory.CreateClient("auth");
            var response = await client.GetAsync(url);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadFromJsonAsync<JsonElement>();
            if (json.TryGetProperty("activities", out var activities))
            {
                return DeserializeDataList(activities);
            }

            return [];
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to fetch user activity data, using sample data");
            return GenerateSampleUserActivityData(dateFrom, dateTo);
        }
    }

    private static List<Dictionary<string, object>> DeserializeDataList(JsonElement element)
    {
        var result = new List<Dictionary<string, object>>();
        if (element.ValueKind != JsonValueKind.Array)
        {
            return result;
        }

        foreach (var item in element.EnumerateArray())
        {
            var dict = new Dictionary<string, object>();
            foreach (var prop in item.EnumerateObject())
            {
                dict[prop.Name] = prop.Value.ValueKind switch
                {
                    JsonValueKind.Number => prop.Value.TryGetInt64(out long l) ? l : prop.Value.GetDouble(),
                    JsonValueKind.True => true,
                    JsonValueKind.False => false,
                    _ => prop.Value.ToString(),
                };
            }

            result.Add(dict);
        }

        return result;
    }

    internal static List<Dictionary<string, object>> GenerateSampleAnalyticsData(DateTime dateFrom, DateTime dateTo)
    {
        string[] eventTypes = ["file_upload", "file_download", "doc_create", "doc_edit", "doc_share", "search_query"];
        string[] users = ["user-001", "user-002", "user-003", "user-004", "user-005"];
        var data = new List<Dictionary<string, object>>();

        for (int i = 0; i < 50; i++)
        {
            data.Add(new Dictionary<string, object>
            {
                ["event_id"] = $"evt-{i:D4}",
                ["event_type"] = eventTypes[i % eventTypes.Length],
                ["user_id"] = users[i % users.Length],
                ["timestamp"] = ReportDateUtils.ToIsoString(dateFrom.AddHours(i))!,
                ["duration_ms"] = 100 + ((i * 17) % 5000),
                ["status"] = i % 10 == 0 ? "error" : "success",
                ["metadata"] = $"sample-analytics-row-{i}",
            });
        }

        return data;
    }

    internal static List<Dictionary<string, object>> GenerateSampleAuditData(DateTime dateFrom, DateTime dateTo)
    {
        string[] actions = ["LOGIN", "LOGOUT", "FILE_ACCESS", "PERMISSION_CHANGE", "ADMIN_ACTION", "API_CALL"];
        string[] results = ["SUCCESS", "FAILURE", "DENIED"];
        var data = new List<Dictionary<string, object>>();

        for (int i = 0; i < 50; i++)
        {
            data.Add(new Dictionary<string, object>
            {
                ["audit_id"] = $"aud-{i:D4}",
                ["action"] = actions[i % actions.Length],
                ["actor"] = $"user-{i % 10:D3}",
                ["result"] = results[i % results.Length],
                ["ip_address"] = $"192.168.1.{i % 255}",
                ["timestamp"] = ReportDateUtils.ToIsoString(dateFrom.AddMinutes(i * 30))!,
                ["resource"] = $"/files/doc-{i % 20}",
                ["details"] = $"Audit entry {i}",
            });
        }

        return data;
    }

    internal static List<Dictionary<string, object>> GenerateSampleUserActivityData(DateTime dateFrom, DateTime dateTo)
    {
        var data = new List<Dictionary<string, object>>();

        for (int i = 0; i < 25; i++)
        {
            data.Add(new Dictionary<string, object>
            {
                ["user_id"] = $"user-{i:D3}",
                ["email"] = $"user{i}@otterworks.example.com",
                ["last_login"] = ReportDateUtils.ToIsoString(ReportDateUtils.DaysAgo(i % 7))!,
                ["files_uploaded"] = 10 + (i * 3),
                ["docs_created"] = 5 + (i * 2),
                ["storage_used_mb"] = 100 + (i * 50),
                ["collaborations"] = i * 4,
                ["active"] = i % 5 != 0,
            });
        }

        return data;
    }
}
