using System.Text.Json;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Options;
using OtterWorks.ReportService.Config;
using OtterWorks.ReportService.Util;

namespace OtterWorks.ReportService.Services;

public class ReportDataFetcher : IReportDataFetcher
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly IMemoryCache _cache;
    private readonly ServiceUrlsSettings _serviceUrls;
    private readonly ILogger<ReportDataFetcher> _logger;
    private static readonly TimeSpan CacheExpiry = TimeSpan.FromMinutes(5);

    public ReportDataFetcher(
        IHttpClientFactory httpClientFactory,
        IMemoryCache cache,
        IOptions<ServiceUrlsSettings> serviceUrls,
        ILogger<ReportDataFetcher> logger)
    {
        _httpClientFactory = httpClientFactory;
        _cache = cache;
        _serviceUrls = serviceUrls.Value;
        _logger = logger;
    }

    public async Task<List<Dictionary<string, object>>> FetchAnalyticsDataAsync(
        DateTime dateFrom, DateTime dateTo, Dictionary<string, string>? parameters)
    {
        var metric = parameters?.GetValueOrDefault("metric");
        var cacheKey = $"analytics:{ReportDateUtils.ToIsoString(dateFrom)}:{ReportDateUtils.ToIsoString(dateTo)}"
                       + (metric != null ? $":metric={metric}" : "");

        if (_cache.TryGetValue(cacheKey, out List<Dictionary<string, object>>? cached) && cached != null)
        {
            return cached;
        }

        try
        {
            var url = $"{_serviceUrls.Analytics}/api/v1/analytics/events?from={ReportDateUtils.ToIsoString(dateFrom)}&to={ReportDateUtils.ToIsoString(dateTo)}";
            if (!string.IsNullOrWhiteSpace(metric))
            {
                url += $"&metric={metric}";
            }

            _logger.LogInformation("Fetching analytics data from: {Url}", url);

            var client = _httpClientFactory.CreateClient("analytics");
            var response = await client.GetAsync(url);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("events", out var events))
            {
                var result = ParseJsonArray(events);
                _cache.Set(cacheKey, result, CacheExpiry);
                return result;
            }

            return new List<Dictionary<string, object>>();
        }
        catch (Exception ex)
        {
            _logger.LogError("Failed to fetch analytics data, using sample data: {Message}", ex.Message);
            return GenerateSampleAnalyticsData(dateFrom, dateTo);
        }
    }

    public async Task<List<Dictionary<string, object>>> FetchAuditDataAsync(
        DateTime dateFrom, DateTime dateTo, Dictionary<string, string>? parameters)
    {
        var cacheKey = $"audit:{ReportDateUtils.ToIsoString(dateFrom)}:{ReportDateUtils.ToIsoString(dateTo)}";

        if (_cache.TryGetValue(cacheKey, out List<Dictionary<string, object>>? cached) && cached != null)
        {
            return cached;
        }

        try
        {
            var url = $"{_serviceUrls.Audit}/api/v1/audit/events?from={ReportDateUtils.ToIsoString(dateFrom)}&to={ReportDateUtils.ToIsoString(dateTo)}";
            _logger.LogInformation("Fetching audit data from: {Url}", url);

            var client = _httpClientFactory.CreateClient("audit");
            var response = await client.GetAsync(url);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("events", out var events))
            {
                var result = ParseJsonArray(events);
                _cache.Set(cacheKey, result, CacheExpiry);
                return result;
            }

            return new List<Dictionary<string, object>>();
        }
        catch (Exception ex)
        {
            _logger.LogError("Failed to fetch audit data, using sample data: {Message}", ex.Message);
            return GenerateSampleAuditData(dateFrom, dateTo);
        }
    }

    public async Task<List<Dictionary<string, object>>> FetchUserActivityDataAsync(
        DateTime dateFrom, DateTime dateTo, Dictionary<string, string>? parameters)
    {
        try
        {
            var url = $"{_serviceUrls.Auth}/api/v1/users/activity?from={ReportDateUtils.ToIsoString(dateFrom)}&to={ReportDateUtils.ToIsoString(dateTo)}";
            _logger.LogInformation("Fetching user activity from: {Url}", url);

            var client = _httpClientFactory.CreateClient("auth");
            var response = await client.GetAsync(url);
            response.EnsureSuccessStatusCode();

            var json = await response.Content.ReadAsStringAsync();
            var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("activities", out var activities))
            {
                return ParseJsonArray(activities);
            }

            return new List<Dictionary<string, object>>();
        }
        catch (Exception ex)
        {
            _logger.LogError("Failed to fetch user activity data: {Message}", ex.Message);
            return GenerateSampleUserActivityData(dateFrom, dateTo);
        }
    }

    private static List<Dictionary<string, object>> ParseJsonArray(JsonElement element)
    {
        var result = new List<Dictionary<string, object>>();
        if (element.ValueKind != JsonValueKind.Array) return result;

        foreach (var item in element.EnumerateArray())
        {
            var dict = new Dictionary<string, object>();
            foreach (var prop in item.EnumerateObject())
            {
                dict[prop.Name] = prop.Value.ValueKind switch
                {
                    JsonValueKind.Number => prop.Value.TryGetInt64(out var l) ? l : prop.Value.GetDouble(),
                    JsonValueKind.True => true,
                    JsonValueKind.False => false,
                    _ => prop.Value.ToString()
                };
            }
            result.Add(dict);
        }
        return result;
    }

    internal static List<Dictionary<string, object>> GenerateSampleAnalyticsData(DateTime dateFrom, DateTime dateTo)
    {
        var data = new List<Dictionary<string, object>>();
        string[] eventTypes = ["file_upload", "file_download", "doc_create", "doc_edit", "doc_share", "search_query"];
        string[] users = ["user-001", "user-002", "user-003", "user-004", "user-005"];

        for (int i = 0; i < 50; i++)
        {
            data.Add(new Dictionary<string, object>
            {
                ["event_id"] = $"evt-{i:D4}",
                ["event_type"] = eventTypes[i % eventTypes.Length],
                ["user_id"] = users[i % users.Length],
                ["timestamp"] = ReportDateUtils.ToIsoString(dateFrom.AddHours(i)),
                ["duration_ms"] = 100 + (i * 17) % 5000,
                ["status"] = i % 10 == 0 ? "error" : "success",
                ["metadata"] = $"sample-analytics-row-{i}"
            });
        }
        return data;
    }

    internal static List<Dictionary<string, object>> GenerateSampleAuditData(DateTime dateFrom, DateTime dateTo)
    {
        var data = new List<Dictionary<string, object>>();
        string[] actions = ["LOGIN", "LOGOUT", "FILE_ACCESS", "PERMISSION_CHANGE", "ADMIN_ACTION", "API_CALL"];
        string[] results = ["SUCCESS", "FAILURE", "DENIED"];

        for (int i = 0; i < 50; i++)
        {
            data.Add(new Dictionary<string, object>
            {
                ["audit_id"] = $"aud-{i:D4}",
                ["action"] = actions[i % actions.Length],
                ["actor"] = $"user-{i % 10:D3}",
                ["result"] = results[i % results.Length],
                ["ip_address"] = $"192.168.1.{i % 255}",
                ["timestamp"] = ReportDateUtils.ToIsoString(dateFrom.AddMinutes(i * 30)),
                ["resource"] = $"/files/doc-{i % 20}",
                ["details"] = $"Audit entry {i}"
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
                ["last_login"] = ReportDateUtils.ToIsoString(DateTime.UtcNow.AddDays(-(i % 7))),
                ["files_uploaded"] = 10 + i * 3,
                ["docs_created"] = 5 + i * 2,
                ["storage_used_mb"] = 100 + i * 50,
                ["collaborations"] = i * 4,
                ["active"] = i % 5 != 0
            });
        }
        return data;
    }
}
