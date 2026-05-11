namespace OtterWorks.SearchService.Models;

public class SuggestResponse
{
    public List<string> Suggestions { get; set; } = new();
    public string Query { get; set; } = string.Empty;

    public object ToDict()
    {
        return new
        {
            suggestions = Suggestions,
            query = Query,
        };
    }
}
