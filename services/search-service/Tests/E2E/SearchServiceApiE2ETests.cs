using System.Net;
using System.Net.Http.Json;
using FluentAssertions;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Moq;
using OtterWorks.SearchService.Models;
using OtterWorks.SearchService.Services;
using Xunit;

namespace OtterWorks.SearchService.Tests.E2E;

public class SearchServiceApiE2ETests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly WebApplicationFactory<Program> _factory;

    public SearchServiceApiE2ETests(WebApplicationFactory<Program> factory)
    {
        _factory = factory.WithWebHostBuilder(builder =>
        {
            builder.ConfigureAppConfiguration((context, config) =>
            {
                config.AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["SearchService:Auth:RequireAuth"] = "false",
                });
            });
            builder.ConfigureServices(services =>
            {
                // Replace MeiliSearch with mock
                services.AddSingleton<IMeiliSearchService>(sp =>
                {
                    var mock = new Mock<IMeiliSearchService>();
                    mock.Setup(m => m.Ping()).Returns(true);
                    mock.Setup(m => m.Search(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<string?>(), It.IsAny<int>(), It.IsAny<int>()))
                        .Returns((string q, string? t, string? o, int p, int s) => new SearchResponse
                        {
                            Results = new List<SearchHit>
                            {
                                new() { Id = "mock-1", Title = "Mock Result", ContentSnippet = "test", Type = "document", OwnerId = "user-1" },
                            },
                            Total = 1, Page = p, PageSize = s, Query = q,
                        });
                    mock.Setup(m => m.AdvancedSearch(It.IsAny<string?>(), It.IsAny<string?>(), It.IsAny<string?>(), It.IsAny<List<string>?>(), It.IsAny<string?>(), It.IsAny<string?>(), It.IsAny<int>(), It.IsAny<int>()))
                        .Returns(new SearchResponse { Results = new(), Total = 0, Page = 1, PageSize = 20, Query = "*" });
                    mock.Setup(m => m.Suggest(It.IsAny<string>(), It.IsAny<int>()))
                        .Returns(new List<string> { "Suggestion 1" });
                    mock.Setup(m => m.DeleteDocument(It.IsAny<string>(), It.IsAny<string>()))
                        .Returns(true);
                    mock.Setup(m => m.Reindex(It.IsAny<List<Dictionary<string, object?>>?>(), It.IsAny<List<Dictionary<string, object?>>?>()))
                        .Returns(new Dictionary<string, object?> { ["status"] = "reindexed" });
                    mock.Setup(m => m.EnsureIndicesAsync()).Returns(Task.CompletedTask);
                    return mock.Object;
                });

                // Replace IndexerService with mock
                services.AddScoped<IIndexerService>(sp =>
                {
                    var mock = new Mock<IIndexerService>();
                    mock.Setup(i => i.IndexDocument(It.IsAny<Dictionary<string, object?>>()))
                        .Returns(new Dictionary<string, string> { ["status"] = "indexed", ["id"] = "doc-1", ["type"] = "document" });
                    mock.Setup(i => i.IndexFile(It.IsAny<Dictionary<string, object?>>()))
                        .Returns(new Dictionary<string, string> { ["status"] = "indexed", ["id"] = "file-1", ["type"] = "file" });
                    mock.Setup(i => i.Remove(It.IsAny<string>(), It.IsAny<string>()))
                        .Returns(new Dictionary<string, object?> { ["status"] = "deleted", ["id"] = "item-1", ["type"] = "document" });
                    mock.Setup(i => i.Reindex())
                        .Returns(new Dictionary<string, object?> { ["status"] = "reindexed" });
                    return mock.Object;
                });
            });
        });
    }

    private HttpClient CreateUnauthenticatedClient() => _factory.CreateClient();

    private HttpClient CreateAuthenticatedClient()
    {
        var client = _factory.CreateClient();
        client.DefaultRequestHeaders.Add("X-User-ID", "test-user");
        return client;
    }

    [Fact]
    public async Task Health_Returns200WithCorrectShape()
    {
        var client = CreateUnauthenticatedClient();
        var response = await client.GetAsync("/health");
        response.StatusCode.Should().Be(HttpStatusCode.OK);

        var json = await response.Content.ReadAsStringAsync();
        json.Should().Contain("\"status\":\"healthy\"");
        json.Should().Contain("\"service\":\"search-service\"");
        json.Should().Contain("\"version\":\"0.1.0\"");
    }

    [Fact]
    public async Task HealthReady_Returns200()
    {
        var client = CreateUnauthenticatedClient();
        var response = await client.GetAsync("/health/ready");
        response.StatusCode.Should().Be(HttpStatusCode.OK);
    }

    [Fact]
    public async Task Search_WithQuery_Returns200()
    {
        var client = CreateAuthenticatedClient();
        var response = await client.GetAsync("/api/v1/search?q=test");
        response.StatusCode.Should().Be(HttpStatusCode.OK);
        var json = await response.Content.ReadAsStringAsync();
        json.Should().Contain("results");
    }

    [Fact]
    public async Task Search_WithoutQuery_Returns400()
    {
        var client = CreateAuthenticatedClient();
        var response = await client.GetAsync("/api/v1/search");
        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task Suggest_WithPrefix_Returns200()
    {
        var client = CreateAuthenticatedClient();
        var response = await client.GetAsync("/api/v1/search/suggest?q=tes");
        response.StatusCode.Should().Be(HttpStatusCode.OK);
    }

    [Fact]
    public async Task AdvancedSearch_Post_Returns200()
    {
        var client = CreateAuthenticatedClient();
        var response = await client.PostAsJsonAsync("/api/v1/search/advanced", new
        {
            q = "test",
            type = "document",
            page = 1,
            size = 10,
        });
        response.StatusCode.Should().Be(HttpStatusCode.OK);
    }

    [Fact]
    public async Task Analytics_Returns200()
    {
        var client = CreateAuthenticatedClient();
        var response = await client.GetAsync("/api/v1/search/analytics");
        response.StatusCode.Should().Be(HttpStatusCode.OK);
    }

    [Fact]
    public async Task IndexDocument_Returns201()
    {
        var client = CreateAuthenticatedClient();
        var response = await client.PostAsJsonAsync("/api/v1/search/index/document", new
        {
            id = "doc-1",
            title = "Test Document",
            content = "body",
            owner_id = "user-1",
        });
        response.StatusCode.Should().Be(HttpStatusCode.Created);
    }

    [Fact]
    public async Task IndexFile_Returns201()
    {
        var client = CreateAuthenticatedClient();
        var response = await client.PostAsJsonAsync("/api/v1/search/index/file", new
        {
            id = "file-1",
            name = "report.pdf",
            mime_type = "application/pdf",
        });
        response.StatusCode.Should().Be(HttpStatusCode.Created);
    }

    [Fact]
    public async Task DeleteFromIndex_Returns200()
    {
        var client = CreateAuthenticatedClient();
        var response = await client.DeleteAsync("/api/v1/search/index/document/doc-1");
        response.StatusCode.Should().Be(HttpStatusCode.OK);
    }

    [Fact]
    public async Task Reindex_Returns200()
    {
        var client = CreateAuthenticatedClient();
        var response = await client.PostAsync("/api/v1/search/reindex", null);
        response.StatusCode.Should().Be(HttpStatusCode.OK);
    }

    [Fact]
    public async Task Swagger_Returns200()
    {
        var client = CreateUnauthenticatedClient();
        var response = await client.GetAsync("/swagger/v1/swagger.json");
        response.StatusCode.Should().Be(HttpStatusCode.OK);
    }

    [Fact]
    public async Task Metrics_Returns200()
    {
        var client = CreateUnauthenticatedClient();
        var response = await client.GetAsync("/metrics");
        response.StatusCode.Should().Be(HttpStatusCode.OK);
    }

    [Fact]
    public async Task ConcurrentSearches_AllSucceed()
    {
        var client = CreateAuthenticatedClient();
        var tasks = Enumerable.Range(0, 5).Select(_ =>
            client.GetAsync("/api/v1/search?q=concurrent"));
        var responses = await Task.WhenAll(tasks);
        responses.Should().AllSatisfy(r => r.StatusCode.Should().Be(HttpStatusCode.OK));
    }
}
