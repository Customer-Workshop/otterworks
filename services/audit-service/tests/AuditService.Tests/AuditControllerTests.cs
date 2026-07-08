using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Moq;
using OtterWorks.AuditService.Models;
using OtterWorks.AuditService.Services;
using IAuditService = OtterWorks.AuditService.Services.IAuditService;

namespace AuditService.Tests;

public class AuditControllerTests : IClassFixture<AuditControllerTests.AuditApiFactory>
{
    private readonly AuditApiFactory _factory;
    private readonly Mock<IAuditService> _mockService;

    public AuditControllerTests(AuditApiFactory factory)
    {
        _factory = factory;
        _mockService = factory.MockService;
        _mockService.Reset();
    }

    private HttpClient Client() => _factory.CreateClient();

    [Fact]
    public async Task RecordEvent_WithValidPayload_Returns201()
    {
        _mockService
            .Setup(s => s.RecordEventAsync(It.IsAny<AuditEventRequest>()))
            .ReturnsAsync(new AuditEventResponse { Id = "evt-1", UserId = "u1", Action = "create" });

        var response = await Client().PostAsJsonAsync("/api/v1/audit/events", new
        {
            userId = "u1",
            action = "create",
            resourceType = "document",
            resourceId = "doc-1",
        });

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        Assert.Equal("/api/v1/audit/events/evt-1", response.Headers.Location?.ToString());
    }

    [Theory]
    [InlineData("", "create", "document", "doc-1")]
    [InlineData("u1", "", "document", "doc-1")]
    [InlineData("u1", "create", "", "doc-1")]
    [InlineData("u1", "create", "document", "")]
    public async Task RecordEvent_WithMissingRequiredFields_Returns400(
        string userId, string action, string resourceType, string resourceId)
    {
        var response = await Client().PostAsJsonAsync("/api/v1/audit/events", new
        {
            userId,
            action,
            resourceType,
            resourceId,
        });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        _mockService.Verify(s => s.RecordEventAsync(It.IsAny<AuditEventRequest>()), Times.Never);
    }

    [Fact]
    public async Task QueryEvents_ClampsPageSizeAndReturns200()
    {
        _mockService
            .Setup(s => s.QueryEventsAsync(
                It.IsAny<string?>(), It.IsAny<string?>(), It.IsAny<string?>(), It.IsAny<string?>(),
                It.IsAny<DateTime?>(), It.IsAny<DateTime?>(), It.IsAny<int>(), It.IsAny<int>()))
            .ReturnsAsync(new AuditEventPage { Total = 0, Page = 1, PageSize = 100 });

        var response = await Client().GetAsync("/api/v1/audit/events?size=500&page=1");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        _mockService.Verify(s => s.QueryEventsAsync(
            null, null, null, null, null, null, 1, 100), Times.Once);
    }

    [Fact]
    public async Task GetEvent_WhenFound_Returns200()
    {
        _mockService
            .Setup(s => s.GetEventAsync("evt-1"))
            .ReturnsAsync(new AuditEventResponse { Id = "evt-1" });

        var response = await Client().GetAsync("/api/v1/audit/events/evt-1");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task GetEvent_WhenNotFound_Returns404()
    {
        _mockService.Setup(s => s.GetEventAsync("missing")).ReturnsAsync((AuditEventResponse?)null);

        var response = await Client().GetAsync("/api/v1/audit/events/missing");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task GetUserActivityReport_DefaultsPeriodTo30d()
    {
        _mockService
            .Setup(s => s.GetUserActivityReportAsync("u1", "30d"))
            .ReturnsAsync(new UserActivityReport { UserId = "u1", Period = "30d" });

        var response = await Client().GetAsync("/api/v1/audit/reports/user/u1");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        _mockService.Verify(s => s.GetUserActivityReportAsync("u1", "30d"), Times.Once);
    }

    [Fact]
    public async Task GetResourceHistory_Returns200()
    {
        _mockService
            .Setup(s => s.GetResourceHistoryAsync("doc-1"))
            .ReturnsAsync(new ResourceHistory { ResourceId = "doc-1" });

        var response = await Client().GetAsync("/api/v1/audit/resources/doc-1/history");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task GetComplianceReport_UsesProvidedPeriod()
    {
        _mockService
            .Setup(s => s.GetComplianceReportAsync("week"))
            .ReturnsAsync(new ComplianceReport { Period = "week" });

        var response = await Client().GetAsync("/api/v1/audit/reports/compliance?period=week");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        _mockService.Verify(s => s.GetComplianceReportAsync("week"), Times.Once);
    }

    [Fact]
    public async Task ExportAuditLog_WithValidFormat_Returns200()
    {
        _mockService
            .Setup(s => s.ExportAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), "csv"))
            .ReturnsAsync(new ExportResult { Format = "csv" });

        var response = await Client().GetAsync("/api/v1/audit/export?format=csv");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        _mockService.Verify(s => s.ExportAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), "csv"), Times.Once);
    }

    [Fact]
    public async Task ExportAuditLog_WithInvalidFormat_Returns400()
    {
        var response = await Client().GetAsync("/api/v1/audit/export?format=xml");

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        _mockService.Verify(
            s => s.ExportAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), It.IsAny<string>()),
            Times.Never);
    }

    [Fact]
    public async Task ArchiveOldEvents_Returns200()
    {
        _mockService
            .Setup(s => s.ArchiveOldEventsAsync())
            .ReturnsAsync(new ArchiveResult { ArchivedCount = 3 });

        var response = await Client().PostAsync("/api/v1/audit/archive", null);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    public sealed class AuditApiFactory : WebApplicationFactory<Program>
    {
        public Mock<IAuditService> MockService { get; } = new();

        protected override void ConfigureWebHost(IWebHostBuilder builder)
        {
            builder.UseEnvironment("Testing");
            builder.ConfigureServices(services =>
            {
                // The SNS consumer would try to reach SQS on startup; not needed for HTTP tests.
                var hostedService = services.SingleOrDefault(
                    d => d.ImplementationType == typeof(SnsConsumer));
                if (hostedService is not null)
                    services.Remove(hostedService);

                var serviceDescriptor = services.SingleOrDefault(d => d.ServiceType == typeof(IAuditService));
                if (serviceDescriptor is not null)
                    services.Remove(serviceDescriptor);

                services.AddSingleton(MockService.Object);
            });
        }
    }
}
