using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Moq;
using OtterWorks.SearchService.Services;

namespace SearchService.Tests.Unit;

public class HealthEndpointTests : IClassFixture<TestWebApplicationFactory>
{
    private readonly HttpClient _client;
    private readonly TestWebApplicationFactory _factory;

    public HealthEndpointTests(TestWebApplicationFactory factory)
    {
        _factory = factory;
        _client = factory.CreateClient();
    }

    [Fact]
    public async Task Health_Returns200WithServiceInfo()
    {
        var response = await _client.GetAsync("/health");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("healthy", json.GetProperty("status").GetString());
        Assert.Equal("search-service", json.GetProperty("service").GetString());
        Assert.Equal("0.1.0", json.GetProperty("version").GetString());
    }

    [Fact]
    public async Task HealthReady_Returns200WhenMeilisearchAvailable()
    {
        _factory.MockMeilisearch.Setup(x => x.PingAsync(It.IsAny<CancellationToken>())).ReturnsAsync(true);

        var response = await _client.GetAsync("/health/ready");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(json.GetProperty("ready").GetBoolean());
    }

    [Fact]
    public async Task HealthReady_Returns503WhenMeilisearchUnavailable()
    {
        _factory.MockMeilisearch.Setup(x => x.PingAsync(It.IsAny<CancellationToken>())).ReturnsAsync(false);

        var response = await _client.GetAsync("/health/ready");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);

        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.False(json.GetProperty("ready").GetBoolean());
    }

    [Fact]
    public async Task Metrics_ReturnsPrometheusFormat()
    {
        var response = await _client.GetAsync("/metrics");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }
}
