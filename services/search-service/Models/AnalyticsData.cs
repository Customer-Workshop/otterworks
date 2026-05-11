namespace OtterWorks.SearchService.Models;

public class AnalyticsData
{
    public List<Dictionary<string, object>> PopularQueries { get; set; } = new();
    public List<Dictionary<string, object>> ZeroResultQueries { get; set; } = new();
    public int TotalSearches { get; set; }
    public double AvgResultsPerQuery { get; set; }

    public object ToDict()
    {
        return new
        {
            popular_queries = PopularQueries,
            zero_result_queries = ZeroResultQueries,
            total_searches = TotalSearches,
            avg_results_per_query = AvgResultsPerQuery,
        };
    }
}
