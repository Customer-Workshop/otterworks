using OtterWorks.SearchService.Models;

namespace OtterWorks.SearchService.Services;

public class SearchAnalyticsStore
{
    private readonly object _lock = new();
    private readonly List<AnalyticsEntry> _queries = [];
    private int _totalSearches;
    private int _totalResults;
    private const int MaxEntries = 10000;

    public void Record(string query, int resultCount)
    {
        lock (_lock)
        {
            _queries.Add(new AnalyticsEntry { Query = query, ResultCount = resultCount, Timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds() });
            _totalSearches++;
            _totalResults += resultCount;
            if (_queries.Count > MaxEntries)
            {
                _queries.RemoveRange(0, _queries.Count - MaxEntries);
            }
        }
    }

    public AnalyticsData GetAnalytics()
    {
        List<AnalyticsEntry> queries;
        int totalSearches;
        int totalResults;

        lock (_lock)
        {
            queries = [.. _queries];
            totalSearches = _totalSearches;
            totalResults = _totalResults;
        }

        var queryCounts = new Dictionary<string, int>();
        var zeroResultCounts = new Dictionary<string, int>();

        foreach (var entry in queries)
        {
            queryCounts[entry.Query] = queryCounts.GetValueOrDefault(entry.Query) + 1;
            if (entry.ResultCount == 0)
            {
                zeroResultCounts[entry.Query] = zeroResultCounts.GetValueOrDefault(entry.Query) + 1;
            }
        }

        var popular = queryCounts.OrderByDescending(x => x.Value).Take(20)
            .Select(x => new QueryCount { Query = x.Key, Count = x.Value }).ToList();
        var zeroResults = zeroResultCounts.OrderByDescending(x => x.Value).Take(20)
            .Select(x => new QueryCount { Query = x.Key, Count = x.Value }).ToList();

        var avgResults = totalSearches > 0 ? Math.Round((double)totalResults / totalSearches, 2) : 0.0;

        return new AnalyticsData
        {
            PopularQueries = popular,
            ZeroResultQueries = zeroResults,
            TotalSearches = totalSearches,
            AvgResultsPerQuery = avgResults,
        };
    }

    private sealed class AnalyticsEntry
    {
        public string Query { get; init; } = string.Empty;
        public int ResultCount { get; init; }
        public long Timestamp { get; init; }
    }
}
