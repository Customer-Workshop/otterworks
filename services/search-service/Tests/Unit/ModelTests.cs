using System.Text.Json;
using OtterWorks.SearchService.Models;

namespace SearchService.Tests.Unit;

public class ModelTests
{
    [Fact]
    public void SearchHit_ToDict_Basic()
    {
        var hit = new SearchHit
        {
            Id = "doc-1",
            Title = "Test",
            ContentSnippet = "snippet",
            Type = "document",
            OwnerId = "user-1",
        };

        var json = JsonSerializer.Serialize(hit);
        var d = JsonSerializer.Deserialize<JsonElement>(json);

        Assert.Equal("doc-1", d.GetProperty("id").GetString());
        Assert.Equal("Test", d.GetProperty("title").GetString());
        Assert.Equal("document", d.GetProperty("type").GetString());
        Assert.False(d.TryGetProperty("created_at", out _));
    }

    [Fact]
    public void SearchHit_ToDict_WithOptionalFields()
    {
        var hit = new SearchHit
        {
            Id = "file-1",
            Title = "report.pdf",
            ContentSnippet = string.Empty,
            Type = "file",
            OwnerId = "user-1",
            MimeType = "application/pdf",
            Size = 1024,
            FolderId = "folder-1",
            CreatedAt = "2024-01-01T00:00:00Z",
            UpdatedAt = "2024-06-01T00:00:00Z",
        };

        var json = JsonSerializer.Serialize(hit);
        var d = JsonSerializer.Deserialize<JsonElement>(json);

        Assert.Equal("application/pdf", d.GetProperty("mime_type").GetString());
        Assert.Equal(1024, d.GetProperty("size").GetInt32());
        Assert.Equal("folder-1", d.GetProperty("folder_id").GetString());
        Assert.Equal("2024-01-01T00:00:00Z", d.GetProperty("created_at").GetString());
    }

    [Fact]
    public void SearchResponse_ToDict()
    {
        var resp = new SearchResponse
        {
            Results =
            [
                new SearchHit { Id = "doc-1", Title = "Test", ContentSnippet = string.Empty, Type = "document", OwnerId = "user-1" },
            ],
            Total = 1,
            Page = 1,
            PageSize = 20,
            Query = "test",
        };

        var json = JsonSerializer.Serialize(resp);
        var d = JsonSerializer.Deserialize<JsonElement>(json);

        Assert.Equal(1, d.GetProperty("total").GetInt32());
        Assert.Equal(1, d.GetProperty("page").GetInt32());
        Assert.Equal(20, d.GetProperty("page_size").GetInt32());
        Assert.Equal("test", d.GetProperty("query").GetString());
        Assert.Equal(1, d.GetProperty("results").GetArrayLength());
    }

    [Fact]
    public void AnalyticsData_ToDict()
    {
        var data = new AnalyticsData
        {
            PopularQueries = [new QueryCount { Query = "test", Count = 5 }],
            ZeroResultQueries = [new QueryCount { Query = "xyz", Count = 2 }],
            TotalSearches = 100,
            AvgResultsPerQuery = 3.5,
        };

        var json = JsonSerializer.Serialize(data);
        var d = JsonSerializer.Deserialize<JsonElement>(json);

        Assert.Equal(100, d.GetProperty("total_searches").GetInt32());
        Assert.Equal(3.5, d.GetProperty("avg_results_per_query").GetDouble());
        Assert.Equal(1, d.GetProperty("popular_queries").GetArrayLength());
        Assert.Equal(1, d.GetProperty("zero_result_queries").GetArrayLength());
    }
}
