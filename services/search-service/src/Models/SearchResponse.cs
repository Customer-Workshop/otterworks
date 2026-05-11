using System.Text.Json.Serialization;

namespace OtterWorks.SearchService.Models;

public class SearchResponse
{
    [JsonPropertyName("results")]
    public List<SearchHit> Results { get; set; } = [];

    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("page")]
    public int Page { get; set; }

    [JsonPropertyName("page_size")]
    public int PageSize { get; set; }

    [JsonPropertyName("query")]
    public string Query { get; set; } = string.Empty;
}
