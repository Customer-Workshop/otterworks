using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using FluentAssertions;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OtterWorks.ReportService.Data;
using OtterWorks.ReportService.Models;
using QuestPDF.Infrastructure;

namespace OtterWorks.ReportService.Tests.Unit;

public class ReportsControllerTests : IClassFixture<WebApplicationFactory<Program>>, IDisposable
{
    private readonly HttpClient _client;
    private readonly WebApplicationFactory<Program> _factory;

    public ReportsControllerTests(WebApplicationFactory<Program> factory)
    {
        QuestPDF.Settings.License = LicenseType.Community;

        _factory = factory.WithWebHostBuilder(builder =>
        {
            builder.ConfigureServices(services =>
            {
                var descriptors = services
                    .Where(d => d.ServiceType == typeof(DbContextOptions<ReportDbContext>)
                        || d.ServiceType == typeof(DbContextOptions)
                        || d.ServiceType.FullName?.Contains("EntityFrameworkCore") == true)
                    .ToList();
                foreach (var d in descriptors)
                {
                    services.Remove(d);
                }

                services.AddDbContext<ReportDbContext>(options =>
                    options.UseInMemoryDatabase("TestDb-" + Guid.NewGuid()));
            });
        });

        _client = _factory.CreateClient();
    }

    public void Dispose()
    {
        _client.Dispose();
        GC.SuppressFinalize(this);
    }

    private static object CreateValidRequest(ReportType type = ReportType.PDF, ReportCategory category = ReportCategory.USAGE_ANALYTICS) =>
        new
        {
            reportName = "Test Report",
            category = category.ToString(),
            reportType = type.ToString(),
            requestedBy = "user-001",
        };

    [Fact]
    public async Task PostValidPdfRequest_Returns202Accepted()
    {
        var response = await _client.PostAsJsonAsync("/api/v1/reports", CreateValidRequest(ReportType.PDF));
        response.StatusCode.Should().Be(HttpStatusCode.Accepted);

        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        body.GetProperty("id").GetInt64().Should().BeGreaterThan(0);
        body.GetProperty("reportName").GetString().Should().Be("Test Report");
        body.GetProperty("category").GetString().Should().Be("USAGE_ANALYTICS");
        body.GetProperty("reportType").GetString().Should().Be("PDF");
        body.GetProperty("status").GetString().Should().Be("PENDING");
    }

    [Fact]
    public async Task PostValidCsvRequest_Returns202Accepted()
    {
        var response = await _client.PostAsJsonAsync("/api/v1/reports", CreateValidRequest(ReportType.CSV));
        response.StatusCode.Should().Be(HttpStatusCode.Accepted);

        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        body.GetProperty("reportType").GetString().Should().Be("CSV");
    }

    [Fact]
    public async Task PostValidExcelRequest_Returns202Accepted()
    {
        var response = await _client.PostAsJsonAsync("/api/v1/reports", CreateValidRequest(ReportType.EXCEL));
        response.StatusCode.Should().Be(HttpStatusCode.Accepted);

        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        body.GetProperty("reportType").GetString().Should().Be("EXCEL");
    }

    [Fact]
    public async Task PostWithoutReportName_Returns400()
    {
        var request = new { category = "USAGE_ANALYTICS", reportType = "PDF", requestedBy = "user-001" };
        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);
        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task PostWithoutCategory_Returns400()
    {
        var request = new { reportName = "Test", reportType = "PDF", requestedBy = "user-001" };
        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);
        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task PostWithoutReportType_Returns400()
    {
        var request = new { reportName = "Test", category = "USAGE_ANALYTICS", requestedBy = "user-001" };
        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);
        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task PostWithoutRequestedBy_Returns400()
    {
        var request = new { reportName = "Test", category = "USAGE_ANALYTICS", reportType = "PDF" };
        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);
        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task GetNonExistentReport_Returns404()
    {
        var response = await _client.GetAsync("/api/v1/reports/99999");
        response.StatusCode.Should().Be(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task GetReportsWithNonExistentUserId_ReturnsEmptyList()
    {
        var response = await _client.GetAsync("/api/v1/reports?userId=nonexistent");
        response.StatusCode.Should().Be(HttpStatusCode.OK);

        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        body.GetProperty("reports").GetArrayLength().Should().Be(0);
        body.GetProperty("total").GetInt32().Should().Be(0);
    }

    [Fact]
    public async Task DownloadNonExistentReport_Returns404()
    {
        var response = await _client.GetAsync("/api/v1/reports/99999/download");
        response.StatusCode.Should().Be(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task DeleteNonExistentReport_Returns404()
    {
        var response = await _client.DeleteAsync("/api/v1/reports/99999");
        response.StatusCode.Should().Be(HttpStatusCode.NotFound);
    }
}

public class HealthControllerTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client;

    public HealthControllerTests(WebApplicationFactory<Program> factory)
    {
        QuestPDF.Settings.License = LicenseType.Community;

        var customFactory = factory.WithWebHostBuilder(builder =>
        {
            builder.ConfigureServices(services =>
            {
                var descriptors = services
                    .Where(d => d.ServiceType == typeof(DbContextOptions<ReportDbContext>)
                        || d.ServiceType == typeof(DbContextOptions)
                        || d.ServiceType.FullName?.Contains("EntityFrameworkCore") == true)
                    .ToList();
                foreach (var d in descriptors)
                {
                    services.Remove(d);
                }

                services.AddDbContext<ReportDbContext>(options =>
                    options.UseInMemoryDatabase("HealthTestDb-" + Guid.NewGuid()));
            });
        });

        _client = customFactory.CreateClient();
    }

    [Fact]
    public async Task GetHealth_Returns200WithCorrectBody()
    {
        var response = await _client.GetAsync("/health");
        response.StatusCode.Should().Be(HttpStatusCode.OK);

        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        body.GetProperty("status").GetString().Should().Be("healthy");
        body.GetProperty("service").GetString().Should().Be("report-service");
        body.GetProperty("version").GetString().Should().Be("0.1.0");
    }
}
