using System.Net;
using FluentAssertions;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;
using Moq.Protected;
using OtterWorks.ReportService.Configuration;
using OtterWorks.ReportService.Services;

namespace OtterWorks.ReportService.Tests.Unit;

public class ReportDataFetcherTests
{
    private readonly ReportDataFetcher _fetcher;
    private readonly Mock<HttpMessageHandler> _handlerMock;
    private readonly IMemoryCache _cache;

    public ReportDataFetcherTests()
    {
        _handlerMock = new Mock<HttpMessageHandler>();
        var httpClient = new HttpClient(_handlerMock.Object);

        var factory = new Mock<IHttpClientFactory>();
        factory.Setup(f => f.CreateClient(It.IsAny<string>())).Returns(httpClient);

        _cache = new MemoryCache(new MemoryCacheOptions());
        var settings = Options.Create(new ReportSettings
        {
            AnalyticsServiceUrl = "http://analytics:8088",
            AuditServiceUrl = "http://audit:8090",
            AuthServiceUrl = "http://auth:8081",
        });
        var logger = new Mock<ILogger<ReportDataFetcher>>();

        _fetcher = new ReportDataFetcher(factory.Object, _cache, settings, logger.Object);
    }

    private void SetupHttpResponse(string responseJson, HttpStatusCode statusCode = HttpStatusCode.OK)
    {
        _handlerMock.Protected()
            .Setup<Task<HttpResponseMessage>>("SendAsync", ItExpr.IsAny<HttpRequestMessage>(), ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = statusCode,
                Content = new StringContent(responseJson, System.Text.Encoding.UTF8, "application/json"),
            });
    }

    [Fact]
    public async Task FetchAnalyticsData_ReturnsEventsFromUpstreamResponse()
    {
        string json = """{"events":[{"event_id":"evt-001","event_type":"file_upload"}]}""";
        SetupHttpResponse(json);

        var result = await _fetcher.FetchAnalyticsDataAsync(DateTime.UtcNow.AddDays(-7), DateTime.UtcNow, null);

        result.Should().HaveCount(1);
        result[0]["event_id"].Should().Be("evt-001");
    }

    [Fact]
    public async Task FetchAnalyticsData_ReturnsSampleDataOnHttpError()
    {
        SetupHttpResponse("{}", HttpStatusCode.InternalServerError);

        var result = await _fetcher.FetchAnalyticsDataAsync(DateTime.UtcNow.AddDays(-7), DateTime.UtcNow, null);

        result.Should().HaveCount(50);
    }

    [Fact]
    public async Task FetchAnalyticsData_IncludesMetricParameterInUrl()
    {
        string json = """{"events":[]}""";
        SetupHttpResponse(json);

        var parameters = new Dictionary<string, string> { { "metric", "cpu" } };
        await _fetcher.FetchAnalyticsDataAsync(DateTime.UtcNow.AddDays(-7), DateTime.UtcNow, parameters);

        _handlerMock.Protected().Verify(
            "SendAsync",
            Times.Once(),
            ItExpr.Is<HttpRequestMessage>(m => m.RequestUri!.ToString().Contains("metric=cpu")),
            ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public async Task FetchAuditData_ReturnsEventsFromUpstreamResponse()
    {
        string json = """{"events":[{"audit_id":"aud-001","action":"LOGIN"}]}""";
        SetupHttpResponse(json);

        var result = await _fetcher.FetchAuditDataAsync(DateTime.UtcNow.AddDays(-7), DateTime.UtcNow, null);

        result.Should().HaveCount(1);
        result[0]["audit_id"].Should().Be("aud-001");
    }

    [Fact]
    public async Task FetchAuditData_ReturnsSampleDataOnHttpError()
    {
        SetupHttpResponse("{}", HttpStatusCode.InternalServerError);

        var result = await _fetcher.FetchAuditDataAsync(DateTime.UtcNow.AddDays(-7), DateTime.UtcNow, null);

        result.Should().HaveCount(50);
    }

    [Fact]
    public async Task FetchUserActivityData_ReturnsActivitiesFromUpstreamResponse()
    {
        string json = """{"activities":[{"user_id":"user-001","email":"a@b.com"}]}""";
        SetupHttpResponse(json);

        var result = await _fetcher.FetchUserActivityDataAsync(DateTime.UtcNow.AddDays(-7), DateTime.UtcNow, null);

        result.Should().HaveCount(1);
        result[0]["user_id"].Should().Be("user-001");
    }

    [Fact]
    public async Task FetchUserActivityData_ReturnsSampleDataOnHttpError()
    {
        SetupHttpResponse("{}", HttpStatusCode.InternalServerError);

        var result = await _fetcher.FetchUserActivityDataAsync(DateTime.UtcNow.AddDays(-7), DateTime.UtcNow, null);

        result.Should().HaveCount(25);
    }

    [Fact]
    public async Task Caching_SecondCallWithin5MinutesReturnsCachedDataWithoutHttpCall()
    {
        string json = """{"events":[{"event_id":"evt-001"}]}""";
        SetupHttpResponse(json);

        var dateFrom = new DateTime(2024, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        var dateTo = new DateTime(2024, 1, 31, 0, 0, 0, DateTimeKind.Utc);

        await _fetcher.FetchAnalyticsDataAsync(dateFrom, dateTo, null);
        await _fetcher.FetchAnalyticsDataAsync(dateFrom, dateTo, null);

        _handlerMock.Protected().Verify(
            "SendAsync",
            Times.Once(),
            ItExpr.IsAny<HttpRequestMessage>(),
            ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public void SampleAnalyticsData_Has50RowsWithCorrectFields()
    {
        var data = ReportDataFetcher.GenerateSampleAnalyticsData(DateTime.UtcNow.AddDays(-7), DateTime.UtcNow);

        data.Should().HaveCount(50);
        data[0].Should().ContainKey("event_id");
        data[0].Should().ContainKey("event_type");
        data[0].Should().ContainKey("user_id");
        data[0].Should().ContainKey("timestamp");
        data[0].Should().ContainKey("duration_ms");
        data[0].Should().ContainKey("status");
        data[0].Should().ContainKey("metadata");
    }
}
