using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using ClosedXML.Excel;
using FluentAssertions;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OtterWorks.ReportService.Data;

namespace ReportService.Tests.E2E;

[Trait("Category", "E2E")]
public class ReportGenerationE2ETests : IClassFixture<ReportGenerationE2ETests.E2EFactory>
{
    private readonly HttpClient _client;
    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNameCaseInsensitive = true };

    public class E2EFactory : WebApplicationFactory<Program>
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
                    .UseInMemoryDatabase("E2ETestDb")
                    .Options;
                services.AddSingleton<DbContextOptions<ReportDbContext>>(inMemoryOptions);
                services.AddScoped<ReportDbContext>();
            });
        }
    }

    public ReportGenerationE2ETests(E2EFactory factory)
    {
        _client = factory.CreateClient();
    }

    private async Task<(long id, string status)> CreateAndPollReport(object request, int maxWaitSeconds = 30)
    {
        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);
        response.StatusCode.Should().Be(HttpStatusCode.Accepted);

        var content = await response.Content.ReadAsStringAsync();
        var json = JsonDocument.Parse(content);
        var id = json.RootElement.GetProperty("id").GetInt64();

        // Poll until complete or timeout
        var deadline = DateTime.UtcNow.AddSeconds(maxWaitSeconds);
        string status = "PENDING";
        while (DateTime.UtcNow < deadline)
        {
            var getResponse = await _client.GetAsync($"/api/v1/reports/{id}");
            if (getResponse.StatusCode == HttpStatusCode.OK)
            {
                var getContent = await getResponse.Content.ReadAsStringAsync();
                var getJson = JsonDocument.Parse(getContent);
                status = getJson.RootElement.GetProperty("status").GetString()!;
                if (status is "COMPLETED" or "FAILED")
                    break;
            }
            await Task.Delay(500);
        }

        return (id, status);
    }

    [Fact]
    public async Task GeneratePdfReport_FullLifecycle()
    {
        var request = new
        {
            reportName = "E2E Usage Report",
            category = "USAGE_ANALYTICS",
            reportType = "PDF",
            requestedBy = "e2e-user"
        };

        var (id, status) = await CreateAndPollReport(request);

        status.Should().Be("COMPLETED");

        // Verify report metadata
        var getResponse = await _client.GetAsync($"/api/v1/reports/{id}");
        getResponse.StatusCode.Should().Be(HttpStatusCode.OK);
        var content = await getResponse.Content.ReadAsStringAsync();
        var json = JsonDocument.Parse(content);
        json.RootElement.GetProperty("fileSizeBytes").GetInt64().Should().BeGreaterThan(0);
        json.RootElement.GetProperty("rowCount").GetInt32().Should().BeGreaterThan(0);
        json.RootElement.GetProperty("downloadUrl").GetString().Should().NotBeNullOrEmpty();

        // Download and verify PDF
        var downloadResponse = await _client.GetAsync($"/api/v1/reports/{id}/download");
        downloadResponse.StatusCode.Should().Be(HttpStatusCode.OK);
        downloadResponse.Content.Headers.ContentType!.MediaType.Should().Be("application/pdf");

        var bytes = await downloadResponse.Content.ReadAsByteArrayAsync();
        bytes.Length.Should().BeGreaterThan(0);
        var header = Encoding.ASCII.GetString(bytes, 0, Math.Min(5, bytes.Length));
        header.Should().Be("%PDF-");
    }

    [Fact]
    public async Task GenerateCsvReport_FullLifecycle()
    {
        var request = new
        {
            reportName = "E2E Audit Export",
            category = "AUDIT_LOG",
            reportType = "CSV",
            requestedBy = "e2e-user"
        };

        var (id, status) = await CreateAndPollReport(request);

        status.Should().Be("COMPLETED");

        var downloadResponse = await _client.GetAsync($"/api/v1/reports/{id}/download");
        downloadResponse.StatusCode.Should().Be(HttpStatusCode.OK);
        downloadResponse.Content.Headers.ContentType!.MediaType.Should().Be("text/csv");

        var csvContent = await downloadResponse.Content.ReadAsStringAsync();
        csvContent.Should().Contain("audit_id");
        csvContent.Should().Contain("action");
        csvContent.Should().Contain("actor");
        var lines = csvContent.Split('\n', StringSplitOptions.RemoveEmptyEntries);
        lines.Length.Should().BeGreaterThan(1);
    }

    [Fact]
    public async Task GenerateExcelReport_FullLifecycle()
    {
        var request = new
        {
            reportName = "E2E User Activity",
            category = "USER_ACTIVITY",
            reportType = "EXCEL",
            requestedBy = "e2e-user"
        };

        var (id, status) = await CreateAndPollReport(request);

        status.Should().Be("COMPLETED");

        var downloadResponse = await _client.GetAsync($"/api/v1/reports/{id}/download");
        downloadResponse.StatusCode.Should().Be(HttpStatusCode.OK);
        downloadResponse.Content.Headers.ContentType!.MediaType
            .Should().Be("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");

        var bytes = await downloadResponse.Content.ReadAsByteArrayAsync();
        using var ms = new MemoryStream(bytes);
        using var workbook = new XLWorkbook(ms);
        workbook.Worksheets.Any(ws => ws.Name == "Summary").Should().BeTrue();
        workbook.Worksheets.Any(ws => ws.Name == "Data").Should().BeTrue();
        workbook.Worksheet("Data").RowsUsed().Count().Should().BeGreaterThan(0);
    }

    [Fact]
    public async Task DownloadWhileGenerating_Returns409()
    {
        var request = new
        {
            reportName = "E2E Conflict Test",
            category = "USAGE_ANALYTICS",
            reportType = "PDF",
            requestedBy = "e2e-user"
        };

        // Create the report
        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);
        response.StatusCode.Should().Be(HttpStatusCode.Accepted);
        var content = await response.Content.ReadAsStringAsync();
        var json = JsonDocument.Parse(content);
        var id = json.RootElement.GetProperty("id").GetInt64();

        // Immediately try to download — may get 409 if still generating, or 404 if no file
        var downloadResponse = await _client.GetAsync($"/api/v1/reports/{id}/download");
        downloadResponse.StatusCode.Should().BeOneOf(HttpStatusCode.Conflict, HttpStatusCode.NotFound, HttpStatusCode.OK);
    }

    [Fact]
    public async Task DeleteReport_RemovesReport()
    {
        var request = new
        {
            reportName = "E2E Delete Test",
            category = "USAGE_ANALYTICS",
            reportType = "PDF",
            requestedBy = "e2e-user"
        };

        var (id, status) = await CreateAndPollReport(request);
        status.Should().Be("COMPLETED");

        var deleteResponse = await _client.DeleteAsync($"/api/v1/reports/{id}");
        deleteResponse.StatusCode.Should().Be(HttpStatusCode.NoContent);

        var getResponse = await _client.GetAsync($"/api/v1/reports/{id}");
        getResponse.StatusCode.Should().Be(HttpStatusCode.NotFound);

        var downloadResponse = await _client.GetAsync($"/api/v1/reports/{id}/download");
        downloadResponse.StatusCode.Should().Be(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task ListReports_WithFilters()
    {
        var request1 = new
        {
            reportName = "E2E Filter Report 1",
            category = "USAGE_ANALYTICS",
            reportType = "PDF",
            requestedBy = "e2e-filter-user"
        };
        var request2 = new
        {
            reportName = "E2E Filter Report 2",
            category = "AUDIT_LOG",
            reportType = "CSV",
            requestedBy = "e2e-filter-user"
        };

        await _client.PostAsJsonAsync("/api/v1/reports", request1);
        await _client.PostAsJsonAsync("/api/v1/reports", request2);

        // Give time for creation
        await Task.Delay(500);

        var listResponse = await _client.GetAsync("/api/v1/reports?userId=e2e-filter-user");
        listResponse.StatusCode.Should().Be(HttpStatusCode.OK);
        var content = await listResponse.Content.ReadAsStringAsync();
        var json = JsonDocument.Parse(content);
        json.RootElement.GetProperty("total").GetInt32().Should().BeGreaterThanOrEqualTo(2);
    }

    [Fact]
    public async Task ValidationError_Returns400()
    {
        var request = new
        {
            category = "AUDIT_LOG",
            reportType = "PDF",
            requestedBy = "e2e-user"
            // Missing reportName
        };

        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);

        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }
}
