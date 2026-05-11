using System.Text.Json.Serialization;

namespace OtterWorks.SearchService.Models;

public class AnalyticsData
{
    [JsonPropertyName("popular_queries")]
    public List<QueryCount> PopularQueries { get; set; } = [];

    [JsonPropertyName("zero_result_queries")]
    public List<QueryCount> ZeroResultQueries { get; set; } = [];

    [JsonPropertyName("total_searches")]
    public int TotalSearches { get; set; }

    [JsonPropertyName("avg_results_per_query")]
    public double AvgResultsPerQuery { get; set; }
}

public class QueryCount
{
    [JsonPropertyName("query")]
    public string Query { get; set; } = string.Empty;

    [JsonPropertyName("count")]
    public int Count { get; set; }
}
