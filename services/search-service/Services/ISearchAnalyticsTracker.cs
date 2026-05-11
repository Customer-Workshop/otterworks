using OtterWorks.SearchService.Models;

namespace OtterWorks.SearchService.Services;

public interface ISearchAnalyticsTracker
{
    void Record(string query, int resultCount);
    AnalyticsData GetAnalytics();
}

public class SearchAnalyticsTracker : ISearchAnalyticsTracker
{
    private readonly object _lock = new();
    private readonly List<(string Query, int ResultCount, double Timestamp)> _queries = new();
    private int _totalSearches;
    private int _totalResults;
    private const int MaxEntries = 10000;

    public void Record(string query, int resultCount)
    {
        lock (_lock)
        {
            _queries.Add((query, resultCount, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0));
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
        List<(string Query, int ResultCount, double Timestamp)> snapshot;
        int totalSearches;
        int totalResults;

        lock (_lock)
        {
            snapshot = new List<(string, int, double)>(_queries);
            totalSearches = _totalSearches;
            totalResults = _totalResults;
        }

        var queryCounts = new Dictionary<string, int>();
        var zeroResultCounts = new Dictionary<string, int>();

        foreach (var entry in snapshot)
        {
            queryCounts[entry.Query] = queryCounts.GetValueOrDefault(entry.Query) + 1;
            if (entry.ResultCount == 0)
            {
                zeroResultCounts[entry.Query] = zeroResultCounts.GetValueOrDefault(entry.Query) + 1;
            }
        }

        var popular = queryCounts
            .OrderByDescending(kv => kv.Value)
            .Take(20)
            .Select(kv => new Dictionary<string, object> { ["query"] = kv.Key, ["count"] = kv.Value })
            .ToList();

        var zeroResults = zeroResultCounts
            .OrderByDescending(kv => kv.Value)
            .Take(20)
            .Select(kv => new Dictionary<string, object> { ["query"] = kv.Key, ["count"] = kv.Value })
            .ToList();

        double avgResults = totalSearches > 0 ? Math.Round((double)totalResults / totalSearches, 2) : 0.0;

        return new AnalyticsData
        {
            PopularQueries = popular,
            ZeroResultQueries = zeroResults,
            TotalSearches = totalSearches,
            AvgResultsPerQuery = avgResults,
        };
    }
}
