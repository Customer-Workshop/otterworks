using System.Net;
using System.Text.Json;

namespace DocumentService.Tests.Unit;

public class HealthTests : IClassFixture<TestWebApplicationFactory>
{
    private readonly HttpClient _client;

    public HealthTests(TestWebApplicationFactory factory)
    {
        _client = factory.CreateClient();
    }

    [Fact]
    public async Task HealthCheck_ReturnsHealthy()
    {
        var response = await _client.GetAsync("/health");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var content = await response.Content.ReadAsStringAsync();
        var data = JsonSerializer.Deserialize<JsonElement>(content);

        Assert.Equal("healthy", data.GetProperty("status").GetString());
        Assert.Equal("document-service", data.GetProperty("service").GetString());
        Assert.Equal("0.1.0", data.GetProperty("version").GetString());
    }

    [Fact]
    public async Task Metrics_ReturnsText()
    {
        var response = await _client.GetAsync("/metrics");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }
}
