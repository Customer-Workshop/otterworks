namespace OtterWorks.SearchService.Models;

public class SearchResponse
{
    public List<SearchHit> Results { get; set; } = new();
    public int Total { get; set; }
    public int Page { get; set; }
    public int PageSize { get; set; }
    public string Query { get; set; } = string.Empty;

    public object ToDict()
    {
        return new
        {
            results = Results.Select(h => h.ToDict()).ToList(),
            total = Total,
            page = Page,
            page_size = PageSize,
            query = Query,
        };
    }
}
