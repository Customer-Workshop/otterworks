using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using FluentAssertions;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OtterWorks.ReportService.Data;
using OtterWorks.ReportService.Models;

namespace ReportService.Tests.Integration;

[Trait("Category", "Integration")]
public class ReportApiIntegrationTests : IClassFixture<ReportApiIntegrationTests.IntegrationFactory>
{
    private readonly HttpClient _client;

    public class IntegrationFactory : WebApplicationFactory<Program>
    {
        protected override void ConfigureWebHost(IWebHostBuilder builder)
        {
            builder.ConfigureServices(services =>
            {
                // Remove existing DbContext and options registrations
                var descriptorsToRemove = services
                    .Where(d => d.ServiceType == typeof(DbContextOptions<ReportDbContext>)
                             || d.ServiceType == typeof(ReportDbContext))
                    .ToList();
                foreach (var d in descriptorsToRemove) services.Remove(d);

                // Register InMemory options as singleton to avoid dual-provider conflict
                var inMemoryOptions = new DbContextOptionsBuilder<ReportDbContext>()
                    .UseInMemoryDatabase("IntegrationTestDb")
                    .Options;
                services.AddSingleton<DbContextOptions<ReportDbContext>>(inMemoryOptions);
                services.AddScoped<ReportDbContext>();
            });
        }
    }

    public ReportApiIntegrationTests(IntegrationFactory factory)
    {
        _client = factory.CreateClient();
    }

    [Fact]
    public async Task HealthEndpoint_ReturnsOk()
    {
        var response = await _client.GetAsync("/health");

        response.StatusCode.Should().Be(HttpStatusCode.OK);

        var content = await response.Content.ReadAsStringAsync();
        var json = JsonDocument.Parse(content);
        json.RootElement.GetProperty("status").GetString().Should().Be("healthy");
        json.RootElement.GetProperty("service").GetString().Should().Be("report-service");
        json.RootElement.GetProperty("version").GetString().Should().Be("0.1.0");
    }

    [Fact]
    public async Task CreateReport_Pdf_ReturnsAccepted()
    {
        var request = new
        {
            reportName = "Test Usage Report",
            category = "USAGE_ANALYTICS",
            reportType = "PDF",
            requestedBy = "test-user-001"
        };

        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);

        response.StatusCode.Should().Be(HttpStatusCode.Accepted);

        var content = await response.Content.ReadAsStringAsync();
        var json = JsonDocument.Parse(content);
        json.RootElement.GetProperty("id").GetInt64().Should().BeGreaterThan(0);
        json.RootElement.GetProperty("reportName").GetString().Should().Be("Test Usage Report");
        json.RootElement.GetProperty("category").GetString().Should().Be("USAGE_ANALYTICS");
        json.RootElement.GetProperty("reportType").GetString().Should().Be("PDF");
        var status = json.RootElement.GetProperty("status").GetString();
        status.Should().BeOneOf("PENDING", "GENERATING", "COMPLETED");
    }

    [Fact]
    public async Task CreateReport_Csv_ReturnsAccepted()
    {
        var request = new
        {
            reportName = "Audit Log Export",
            category = "AUDIT_LOG",
            reportType = "CSV",
            requestedBy = "test-user-002"
        };

        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);

        response.StatusCode.Should().Be(HttpStatusCode.Accepted);
        var content = await response.Content.ReadAsStringAsync();
        var json = JsonDocument.Parse(content);
        json.RootElement.GetProperty("reportType").GetString().Should().Be("CSV");
    }

    [Fact]
    public async Task CreateReport_Excel_ReturnsAccepted()
    {
        var request = new
        {
            reportName = "User Activity Summary",
            category = "USER_ACTIVITY",
            reportType = "EXCEL",
            requestedBy = "test-user-003"
        };

        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);

        response.StatusCode.Should().Be(HttpStatusCode.Accepted);
        var content = await response.Content.ReadAsStringAsync();
        var json = JsonDocument.Parse(content);
        json.RootElement.GetProperty("reportType").GetString().Should().Be("EXCEL");
    }

    [Fact]
    public async Task GetReport_NotFound_Returns404()
    {
        var response = await _client.GetAsync("/api/v1/reports/99999");

        response.StatusCode.Should().Be(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task ListReports_NonexistentUser_ReturnsEmptyList()
    {
        var response = await _client.GetAsync("/api/v1/reports?userId=nonexistent-user");

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        var content = await response.Content.ReadAsStringAsync();
        var json = JsonDocument.Parse(content);
        json.RootElement.GetProperty("reports").GetArrayLength().Should().Be(0);
        json.RootElement.GetProperty("total").GetInt32().Should().Be(0);
    }

    [Fact]
    public async Task CreateReport_MissingName_Returns400()
    {
        var request = new
        {
            category = "AUDIT_LOG",
            reportType = "PDF",
            requestedBy = "test-user"
        };

        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);

        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task DownloadReport_NotFound_Returns404()
    {
        var response = await _client.GetAsync("/api/v1/reports/99999/download");

        response.StatusCode.Should().Be(HttpStatusCode.NotFound);
    }
}
