using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Moq;
using OtterWorks.SearchService.Models;
using OtterWorks.SearchService.Services;

namespace SearchService.Tests.Unit;

public class SearchEndpointTests : IClassFixture<TestWebApplicationFactory>
{
    private readonly HttpClient _client;
    private readonly TestWebApplicationFactory _factory;

    public SearchEndpointTests(TestWebApplicationFactory factory)
    {
        _factory = factory;
        _client = factory.CreateClient();
    }

    [Fact]
    public async Task Search_WithoutQuery_Returns400()
    {
        var response = await _client.GetAsync("/api/v1/search/");
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(json.TryGetProperty("error", out _));
    }

    [Fact]
    public async Task Search_WithQuery_ReturnsResults()
    {
        _factory.MockMeilisearch.Setup(x => x.SearchAsync(
                "test", null, null, 1, 20, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new SearchResponse
            {
                Results =
                [
                    new SearchHit
                    {
                        Id = "doc-1",
                        Title = "Test Document",
                        ContentSnippet = "Some content here",
                        Type = "document",
                        OwnerId = "user-1",
                        Tags = ["test"],
                    },
                ],
                Total = 1,
                Page = 1,
                PageSize = 20,
                Query = "test",
            });

        var response = await _client.GetAsync("/api/v1/search/?q=test");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(json.GetProperty("total").GetInt32() >= 1);
        Assert.True(json.GetProperty("results").GetArrayLength() >= 1);
        Assert.Equal("test", json.GetProperty("query").GetString());
    }

    [Fact]
    public async Task Search_WithTypeFilter_Returns200()
    {
        _factory.MockMeilisearch.Setup(x => x.SearchAsync(
                "test", "file", null, 1, 20, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new SearchResponse { Results = [], Total = 0, Page = 1, PageSize = 20, Query = "test" });

        var response = await _client.GetAsync("/api/v1/search/?q=test&type=file");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task Search_WithPagination_ReturnsCorrectPage()
    {
        _factory.MockMeilisearch.Setup(x => x.SearchAsync(
                "test", null, null, 2, 10, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new SearchResponse { Results = [], Total = 0, Page = 2, PageSize = 10, Query = "test" });

        var response = await _client.GetAsync("/api/v1/search/?q=test&page=2&size=10");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(2, json.GetProperty("page").GetInt32());
        Assert.Equal(10, json.GetProperty("page_size").GetInt32());
    }

    [Fact]
    public async Task Search_InvalidPage_Returns400()
    {
        var response = await _client.GetAsync("/api/v1/search/?q=test&page=not-a-number");
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task Suggest_ShortQuery_ReturnsEmpty()
    {
        var response = await _client.GetAsync("/api/v1/search/suggest?q=a");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(0, json.GetProperty("suggestions").GetArrayLength());
    }

    [Fact]
    public async Task Suggest_WithPrefix_ReturnsSuggestions()
    {
        _factory.MockMeilisearch.Setup(x => x.SuggestAsync("te", 10, It.IsAny<CancellationToken>()))
            .ReturnsAsync(["Test Doc 1", "Test Doc 2"]);

        var response = await _client.GetAsync("/api/v1/search/suggest?q=te");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(json.GetProperty("suggestions").GetArrayLength() >= 1);
    }

    [Fact]
    public async Task Suggest_EmptyQuery_ReturnsEmpty()
    {
        var response = await _client.GetAsync("/api/v1/search/suggest?q=");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(0, json.GetProperty("suggestions").GetArrayLength());
    }

    [Fact]
    public async Task AdvancedSearch_WithFilters_ReturnsResults()
    {
        _factory.MockMeilisearch.Setup(x => x.AdvancedSearchAsync(
                "report", "document", null, It.IsAny<List<string>>(), "2024-01-01", "2024-12-31", 1, 10, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new SearchResponse { Results = [], Total = 0, Page = 1, PageSize = 10, Query = "report" });

        var body = JsonSerializer.Serialize(new
        {
            q = "report",
            type = "document",
            owner_id = "user-1",
            tags = new[] { "finance" },
            date_from = "2024-01-01",
            date_to = "2024-12-31",
            page = 1,
            size = 10,
        });

        var response = await _client.PostAsync("/api/v1/search/advanced",
            new StringContent(body, Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(json.TryGetProperty("results", out _));
        Assert.True(json.TryGetProperty("total", out _));
    }

    [Fact]
    public async Task AdvancedSearch_EmptyBody_Returns200()
    {
        _factory.MockMeilisearch.Setup(x => x.AdvancedSearchAsync(
                null, null, null, null, null, null, 1, 20, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new SearchResponse { Results = [], Total = 0, Page = 1, PageSize = 20, Query = "*" });

        var response = await _client.PostAsync("/api/v1/search/advanced",
            new StringContent("{}", Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task Analytics_ReturnsData()
    {
        _factory.MockMeilisearch.Setup(x => x.GetAnalytics())
            .Returns(new AnalyticsData
            {
                PopularQueries = [],
                ZeroResultQueries = [],
                TotalSearches = 0,
                AvgResultsPerQuery = 0.0,
            });

        var response = await _client.GetAsync("/api/v1/search/analytics");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(json.TryGetProperty("popular_queries", out _));
        Assert.True(json.TryGetProperty("zero_result_queries", out _));
        Assert.True(json.TryGetProperty("total_searches", out _));
        Assert.True(json.TryGetProperty("avg_results_per_query", out _));
    }
}
