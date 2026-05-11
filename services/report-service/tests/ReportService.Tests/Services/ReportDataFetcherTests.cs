using System.Net;
using System.Text.Json;
using FluentAssertions;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Logging;
using Moq;
using Moq.Protected;
using OtterWorks.ReportService.Services;

namespace ReportService.Tests.Services;

public class ReportDataFetcherTests
{
    private readonly Mock<IHttpClientFactory> _httpClientFactory;
    private readonly IMemoryCache _cache;
    private readonly ReportDataFetcher _fetcher;

    public ReportDataFetcherTests()
    {
        _httpClientFactory = new Mock<IHttpClientFactory>();
        _cache = new MemoryCache(new MemoryCacheOptions());
        var logger = new Mock<ILogger<ReportDataFetcher>>();
        _fetcher = new ReportDataFetcher(_httpClientFactory.Object, _cache, logger.Object);
    }

    private void SetupHttpClient(string clientName, HttpStatusCode statusCode, string responseContent)
    {
        var handler = new Mock<HttpMessageHandler>();
        handler.Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = statusCode,
                Content = new StringContent(responseContent)
            });

        var client = new HttpClient(handler.Object) { BaseAddress = new Uri("http://test:8080") };
        _httpClientFactory.Setup(f => f.CreateClient(clientName)).Returns(client);
    }

    [Fact]
    public async Task FetchAnalyticsData_WithSuccessfulResponse_ShouldReturnEvents()
    {
        var events = new[]
        {
            new { event_id = "evt-001", event_type = "file_upload" },
            new { event_id = "evt-002", event_type = "doc_create" }
        };
        var response = JsonSerializer.Serialize(new { events });
        SetupHttpClient("analytics", HttpStatusCode.OK, response);

        var result = await _fetcher.FetchAnalyticsDataAsync(
            DateTime.UtcNow.AddDays(-7), DateTime.UtcNow, null);

        result.Should().HaveCount(2);
        result[0]["event_id"].Should().Be("evt-001");
    }

    [Fact]
    public async Task FetchAnalyticsData_WithFailure_ShouldReturnSampleData()
    {
        SetupHttpClient("analytics", HttpStatusCode.InternalServerError, "error");

        var result = await _fetcher.FetchAnalyticsDataAsync(
            DateTime.UtcNow.AddDays(-7), DateTime.UtcNow, null);

        result.Should().HaveCount(50);
        result[0].Should().ContainKey("event_id");
    }

    [Fact]
    public async Task FetchAuditData_WithCacheHit_ShouldNotCallHttp()
    {
        var events = new[]
        {
            new { audit_id = "aud-001", action = "LOGIN" }
        };
        var response = JsonSerializer.Serialize(new { events });
        SetupHttpClient("audit", HttpStatusCode.OK, response);

        var dateFrom = new DateTime(2024, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        var dateTo = new DateTime(2024, 1, 31, 0, 0, 0, DateTimeKind.Utc);

        var result1 = await _fetcher.FetchAuditDataAsync(dateFrom, dateTo, null);
        result1.Should().HaveCount(1);

        // Second call should use cache
        var result2 = await _fetcher.FetchAuditDataAsync(dateFrom, dateTo, null);
        result2.Should().HaveCount(1);

        _httpClientFactory.Verify(f => f.CreateClient("audit"), Times.Once);
    }

    [Fact]
    public async Task FetchUserActivityData_ShouldReturnActivities()
    {
        var activities = new[]
        {
            new { user_id = "user-001", email = "user@test.com" }
        };
        var response = JsonSerializer.Serialize(new { activities });
        SetupHttpClient("auth", HttpStatusCode.OK, response);

        var result = await _fetcher.FetchUserActivityDataAsync(
            DateTime.UtcNow.AddDays(-7), DateTime.UtcNow, null);

        result.Should().HaveCount(1);
        result[0]["user_id"].Should().Be("user-001");
    }
}
