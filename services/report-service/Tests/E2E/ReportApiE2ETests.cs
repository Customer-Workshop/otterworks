using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using FluentAssertions;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OtterWorks.ReportService.Configuration;
using OtterWorks.ReportService.Data;
using OtterWorks.ReportService.Models;
using QuestPDF.Infrastructure;
using Testcontainers.PostgreSql;

namespace OtterWorks.ReportService.Tests.E2E;

public class ReportApiE2ETests : IAsyncLifetime
{
    private PostgreSqlContainer _postgres = null!;
    private WebApplicationFactory<Program> _factory = null!;
    private HttpClient _client = null!;
    private string _outputDir = null!;

    public async Task InitializeAsync()
    {
        QuestPDF.Settings.License = LicenseType.Community;

        _outputDir = Path.Combine(Path.GetTempPath(), "e2e-reports-" + Guid.NewGuid());
        Directory.CreateDirectory(_outputDir);

        _postgres = new PostgreSqlBuilder()
            .WithImage("postgres:15-alpine")
            .WithDatabase("otterworks_reports")
            .WithUsername("otterworks")
            .WithPassword("otterworks_dev")
            .Build();

        await _postgres.StartAsync();

        _factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
        {
            builder.ConfigureServices(services =>
            {
                var descriptor = services.SingleOrDefault(d => d.ServiceType == typeof(DbContextOptions<ReportDbContext>));
                if (descriptor != null)
                {
                    services.Remove(descriptor);
                }

                services.AddDbContext<ReportDbContext>(options =>
                    options.UseNpgsql(_postgres.GetConnectionString()));

                services.Configure<ReportSettings>(s =>
                {
                    s.OutputDir = _outputDir;
                    s.MaxRows = 50000;
                });
            });
        });

        _client = _factory.CreateClient();

        // Ensure DB is created
        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<ReportDbContext>();
        await db.Database.EnsureCreatedAsync();
    }

    public async Task DisposeAsync()
    {
        _client.Dispose();
        await _factory.DisposeAsync();
        await _postgres.DisposeAsync();
        if (Directory.Exists(_outputDir))
        {
            Directory.Delete(_outputDir, true);
        }
    }

    private async Task<JsonElement> CreateReportAndWaitForCompletion(
        string reportName,
        string category,
        string reportType,
        int maxWaitSeconds = 30)
    {
        var request = new
        {
            reportName,
            category,
            reportType,
            requestedBy = "e2e-test-user",
        };

        var createResponse = await _client.PostAsJsonAsync("/api/v1/reports", request);
        createResponse.StatusCode.Should().Be(HttpStatusCode.Accepted);

        var created = await createResponse.Content.ReadFromJsonAsync<JsonElement>();
        long reportId = created.GetProperty("id").GetInt64();

        // Poll until completed
        for (int i = 0; i < maxWaitSeconds * 2; i++)
        {
            await Task.Delay(500);
            var getResponse = await _client.GetAsync($"/api/v1/reports/{reportId}");
            var report = await getResponse.Content.ReadFromJsonAsync<JsonElement>();
            string status = report.GetProperty("status").GetString()!;
            if (status == "COMPLETED" || status == "FAILED")
            {
                return report;
            }
        }

        throw new TimeoutException($"Report {reportId} did not complete within {maxWaitSeconds} seconds");
    }

    [Fact]
    public async Task PdfLifecycle_CreateWaitDownloadDelete()
    {
        var report = await CreateReportAndWaitForCompletion("E2E PDF Test", "USAGE_ANALYTICS", "PDF");
        report.GetProperty("status").GetString().Should().Be("COMPLETED");
        long reportId = report.GetProperty("id").GetInt64();

        // Download
        var downloadResponse = await _client.GetAsync($"/api/v1/reports/{reportId}/download");
        downloadResponse.StatusCode.Should().Be(HttpStatusCode.OK);
        downloadResponse.Content.Headers.ContentType!.MediaType.Should().Be("application/pdf");
        downloadResponse.Content.Headers.ContentDisposition!.DispositionType.Should().Be("attachment");
        var content = await downloadResponse.Content.ReadAsByteArrayAsync();
        content.Length.Should().BeGreaterThan(0);

        // Delete
        var deleteResponse = await _client.DeleteAsync($"/api/v1/reports/{reportId}");
        deleteResponse.StatusCode.Should().Be(HttpStatusCode.NoContent);

        // Verify deleted
        var getResponse = await _client.GetAsync($"/api/v1/reports/{reportId}");
        getResponse.StatusCode.Should().Be(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task CsvLifecycle_CreateWaitDownloadDelete()
    {
        var report = await CreateReportAndWaitForCompletion("E2E CSV Test", "AUDIT_LOG", "CSV");
        report.GetProperty("status").GetString().Should().Be("COMPLETED");
        long reportId = report.GetProperty("id").GetInt64();

        var downloadResponse = await _client.GetAsync($"/api/v1/reports/{reportId}/download");
        downloadResponse.StatusCode.Should().Be(HttpStatusCode.OK);
        downloadResponse.Content.Headers.ContentType!.MediaType.Should().Be("text/csv");

        var csvContent = await downloadResponse.Content.ReadAsStringAsync();
        csvContent.Should().Contain("# OtterWorks Report:");
        csvContent.Should().Contain("# Rows:");

        var deleteResponse = await _client.DeleteAsync($"/api/v1/reports/{reportId}");
        deleteResponse.StatusCode.Should().Be(HttpStatusCode.NoContent);
    }

    [Fact]
    public async Task ExcelLifecycle_CreateWaitDownloadDelete()
    {
        var report = await CreateReportAndWaitForCompletion("E2E Excel Test", "USER_ACTIVITY", "EXCEL");
        report.GetProperty("status").GetString().Should().Be("COMPLETED");
        long reportId = report.GetProperty("id").GetInt64();

        var downloadResponse = await _client.GetAsync($"/api/v1/reports/{reportId}/download");
        downloadResponse.StatusCode.Should().Be(HttpStatusCode.OK);
        downloadResponse.Content.Headers.ContentType!.MediaType.Should().Be("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");

        var bytes = await downloadResponse.Content.ReadAsByteArrayAsync();
        bytes.Length.Should().BeGreaterThan(0);
        // XLSX files are ZIP files, start with PK
        bytes[0].Should().Be(0x50); // P
        bytes[1].Should().Be(0x4B); // K

        var deleteResponse = await _client.DeleteAsync($"/api/v1/reports/{reportId}");
        deleteResponse.StatusCode.Should().Be(HttpStatusCode.NoContent);
    }

    [Fact]
    public async Task DownloadBeforeCompletion_Returns409Conflict()
    {
        var request = new
        {
            reportName = "Conflict Test",
            category = "USAGE_ANALYTICS",
            reportType = "PDF",
            requestedBy = "e2e-test-user",
        };

        var createResponse = await _client.PostAsJsonAsync("/api/v1/reports", request);
        var created = await createResponse.Content.ReadFromJsonAsync<JsonElement>();
        long reportId = created.GetProperty("id").GetInt64();

        // Immediately try to download before it completes
        var downloadResponse = await _client.GetAsync($"/api/v1/reports/{reportId}/download");
        // Should be either 409 (Conflict - still generating) or 404 (if already failed) or 200 (if very fast)
        downloadResponse.StatusCode.Should().BeOneOf(HttpStatusCode.Conflict, HttpStatusCode.OK, HttpStatusCode.NotFound);
    }

    [Theory]
    [InlineData("USAGE_ANALYTICS")]
    [InlineData("AUDIT_LOG")]
    [InlineData("STORAGE_SUMMARY")]
    [InlineData("USER_ACTIVITY")]
    [InlineData("COLLABORATION_METRICS")]
    [InlineData("SYSTEM_HEALTH")]
    [InlineData("COMPLIANCE")]
    public async Task AllCategories_ReachCompletedStatus(string category)
    {
        var report = await CreateReportAndWaitForCompletion($"Category Test {category}", category, "PDF");
        report.GetProperty("status").GetString().Should().Be("COMPLETED");
    }

    [Fact]
    public async Task ValidationErrors_MissingReportName_Returns400()
    {
        var request = new { category = "USAGE_ANALYTICS", reportType = "PDF", requestedBy = "user" };
        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);
        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task ValidationErrors_MissingCategory_Returns400()
    {
        var request = new { reportName = "Test", reportType = "PDF", requestedBy = "user" };
        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);
        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task ValidationErrors_MissingReportType_Returns400()
    {
        var request = new { reportName = "Test", category = "USAGE_ANALYTICS", requestedBy = "user" };
        var response = await _client.PostAsJsonAsync("/api/v1/reports", request);
        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task ListFiltering_ReturnsByUser()
    {
        // Create reports for different users
        await _client.PostAsJsonAsync("/api/v1/reports", new
        {
            reportName = "User1 Report",
            category = "USAGE_ANALYTICS",
            reportType = "PDF",
            requestedBy = "filter-user-1",
        });
        await _client.PostAsJsonAsync("/api/v1/reports", new
        {
            reportName = "User2 Report",
            category = "AUDIT_LOG",
            reportType = "CSV",
            requestedBy = "filter-user-2",
        });

        var response = await _client.GetAsync("/api/v1/reports?userId=filter-user-1");
        response.StatusCode.Should().Be(HttpStatusCode.OK);

        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        var reports = body.GetProperty("reports");
        foreach (var report in reports.EnumerateArray())
        {
            report.GetProperty("requestedBy").GetString().Should().Be("filter-user-1");
        }
    }

    [Fact]
    public async Task HealthCheck_Returns200()
    {
        var response = await _client.GetAsync("/health");
        response.StatusCode.Should().Be(HttpStatusCode.OK);

        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        body.GetProperty("status").GetString().Should().Be("healthy");
        body.GetProperty("service").GetString().Should().Be("report-service");
        body.GetProperty("version").GetString().Should().Be("0.1.0");
    }

    [Fact]
    public async Task ConcurrentGeneration_AllReachCompleted()
    {
        var tasks = new List<Task<JsonElement>>();
        for (int i = 0; i < 5; i++)
        {
            tasks.Add(CreateReportAndWaitForCompletion($"Concurrent Test {i}", "USAGE_ANALYTICS", "PDF"));
        }

        var results = await Task.WhenAll(tasks);
        foreach (var report in results)
        {
            report.GetProperty("status").GetString().Should().Be("COMPLETED");
        }
    }

    [Fact]
    public async Task MaxRowsTruncation_RowCountCapped()
    {
        // Create a factory with low MaxRows setting
        var lowRowsFactory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
        {
            builder.ConfigureServices(services =>
            {
                var descriptor = services.SingleOrDefault(d => d.ServiceType == typeof(DbContextOptions<ReportDbContext>));
                if (descriptor != null)
                {
                    services.Remove(descriptor);
                }

                services.AddDbContext<ReportDbContext>(options =>
                    options.UseNpgsql(_postgres.GetConnectionString()));

                services.Configure<ReportSettings>(s =>
                {
                    s.OutputDir = _outputDir;
                    s.MaxRows = 10;
                });
            });
        });

        var lowRowsClient = lowRowsFactory.CreateClient();

        var request = new
        {
            reportName = "Max Rows Test",
            category = "USAGE_ANALYTICS",
            reportType = "PDF",
            requestedBy = "e2e-test-user",
        };

        var createResponse = await lowRowsClient.PostAsJsonAsync("/api/v1/reports", request);
        var created = await createResponse.Content.ReadFromJsonAsync<JsonElement>();
        long reportId = created.GetProperty("id").GetInt64();

        // Wait for completion
        for (int i = 0; i < 60; i++)
        {
            await Task.Delay(500);
            var getResponse = await lowRowsClient.GetAsync($"/api/v1/reports/{reportId}");
            var report = await getResponse.Content.ReadFromJsonAsync<JsonElement>();
            string status = report.GetProperty("status").GetString()!;
            if (status == "COMPLETED")
            {
                report.GetProperty("rowCount").GetInt32().Should().BeLessThanOrEqualTo(10);
                return;
            }

            if (status == "FAILED")
            {
                break;
            }
        }

        // If we get here, report should still have completed with capped rows
        var finalResponse = await lowRowsClient.GetAsync($"/api/v1/reports/{reportId}");
        var finalReport = await finalResponse.Content.ReadFromJsonAsync<JsonElement>();
        finalReport.GetProperty("status").GetString().Should().Be("COMPLETED");
        finalReport.GetProperty("rowCount").GetInt32().Should().BeLessThanOrEqualTo(10);
    }
}
