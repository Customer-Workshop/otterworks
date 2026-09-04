using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;
using Moq;
using OtterWorks.AuditService.Models;
using OtterWorks.AuditService.Services;

namespace AuditService.Tests;

public class AuditAuthorizationTests : IClassFixture<AuditApiFactory>
{
    private const string Owner = "user-owner";
    private const string Other = "user-other";
    private const string Admin = "admin-1";
    private const string ServiceAccount = "svc-file-service";

    private readonly AuditApiFactory _factory;
    private readonly Mock<IAuditService> _auditService;

    public AuditAuthorizationTests(AuditApiFactory factory)
    {
        _factory = factory;
        _auditService = factory.AuditService;
        _auditService.Reset();
    }

    private HttpClient Client(string? callerId)
    {
        var client = _factory.CreateClient();
        if (callerId is not null)
        {
            client.DefaultRequestHeaders.Add("X-User-ID", callerId);
        }

        return client;
    }

    // GET /api/v1/audit/events/{id}

    [Fact]
    public async Task GetEvent_AsOwner_ReturnsEvent()
    {
        _auditService.Setup(s => s.GetEventAsync("evt-1")).ReturnsAsync(Response("evt-1", Owner));

        var response = await Client(Owner).GetAsync("/api/v1/audit/events/evt-1");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task GetEvent_AsOtherUser_IsHiddenBehindNotFound()
    {
        _auditService.Setup(s => s.GetEventAsync("evt-1")).ReturnsAsync(Response("evt-1", Owner));

        var response = await Client(Other).GetAsync("/api/v1/audit/events/evt-1");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task GetEvent_AsAdmin_ReturnsEvent()
    {
        _auditService.Setup(s => s.GetEventAsync("evt-1")).ReturnsAsync(Response("evt-1", Owner));

        var response = await Client(Admin).GetAsync("/api/v1/audit/events/evt-1");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task GetEvent_WithoutCallerHeader_IsUnauthorized()
    {
        var response = await Client(null).GetAsync("/api/v1/audit/events/evt-1");

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        _auditService.Verify(s => s.GetEventAsync(It.IsAny<string>()), Times.Never);
    }

    [Fact]
    public async Task GetEvent_WithBlankCallerHeader_IsUnauthorized()
    {
        var client = _factory.CreateClient();
        client.DefaultRequestHeaders.Add("X-User-ID", "   ");

        var response = await client.GetAsync("/api/v1/audit/events/evt-1");

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    // GET /api/v1/audit/events

    [Fact]
    public async Task QueryEvents_WithoutFilter_IsScopedToCaller()
    {
        _auditService
            .Setup(s => s.QueryEventsAsync(Owner, null, null, null, null, null, 1, 20))
            .ReturnsAsync(new AuditEventPage());

        var response = await Client(Owner).GetAsync("/api/v1/audit/events");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        _auditService.Verify(
            s => s.QueryEventsAsync(Owner, null, null, null, null, null, 1, 20), Times.Once);
    }

    [Fact]
    public async Task QueryEvents_ForAnotherUser_IsForbidden()
    {
        var response = await Client(Owner).GetAsync($"/api/v1/audit/events?user_id={Other}");

        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        _auditService.Verify(
            s => s.QueryEventsAsync(It.IsAny<string?>(), It.IsAny<string?>(), It.IsAny<string?>(),
                It.IsAny<string?>(), It.IsAny<DateTime?>(), It.IsAny<DateTime?>(), It.IsAny<int>(), It.IsAny<int>()),
            Times.Never);
    }

    [Fact]
    public async Task QueryEvents_AsAdmin_MayFilterByAnyUser()
    {
        _auditService
            .Setup(s => s.QueryEventsAsync(Other, null, null, null, null, null, 1, 20))
            .ReturnsAsync(new AuditEventPage());

        var response = await Client(Admin).GetAsync($"/api/v1/audit/events?user_id={Other}");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        _auditService.Verify(
            s => s.QueryEventsAsync(Other, null, null, null, null, null, 1, 20), Times.Once);
    }

    [Fact]
    public async Task QueryEvents_WithoutCallerHeader_IsUnauthorized()
    {
        var response = await Client(null).GetAsync("/api/v1/audit/events");

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    // GET /api/v1/audit/reports/user/{userId}

    [Fact]
    public async Task UserActivityReport_ForSelf_IsAllowed()
    {
        _auditService
            .Setup(s => s.GetUserActivityReportAsync(Owner, "30d"))
            .ReturnsAsync(new UserActivityReport { UserId = Owner });

        var response = await Client(Owner).GetAsync($"/api/v1/audit/reports/user/{Owner}");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task UserActivityReport_ForAnotherUser_IsForbidden()
    {
        var response = await Client(Owner).GetAsync($"/api/v1/audit/reports/user/{Other}");

        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        _auditService.Verify(
            s => s.GetUserActivityReportAsync(It.IsAny<string>(), It.IsAny<string>()), Times.Never);
    }

    [Fact]
    public async Task UserActivityReport_AsAdmin_IsAllowedForAnyUser()
    {
        _auditService
            .Setup(s => s.GetUserActivityReportAsync(Other, "30d"))
            .ReturnsAsync(new UserActivityReport { UserId = Other });

        var response = await Client(Admin).GetAsync($"/api/v1/audit/reports/user/{Other}");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task UserActivityReport_WithoutCallerHeader_IsUnauthorized()
    {
        var response = await Client(null).GetAsync($"/api/v1/audit/reports/user/{Owner}");

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    // GET /api/v1/audit/resources/{resourceId}/history

    [Fact]
    public async Task ResourceHistory_ForUnprivilegedCaller_IsRestrictedToTheirOwnEvents()
    {
        _auditService
            .Setup(s => s.GetResourceHistoryAsync("doc-1", Owner))
            .ReturnsAsync(new ResourceHistory { ResourceId = "doc-1" });

        var response = await Client(Owner).GetAsync("/api/v1/audit/resources/doc-1/history");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        _auditService.Verify(s => s.GetResourceHistoryAsync("doc-1", Owner), Times.Once);
    }

    [Fact]
    public async Task ResourceHistory_AsAdmin_ReturnsFullHistory()
    {
        _auditService
            .Setup(s => s.GetResourceHistoryAsync("doc-1", null))
            .ReturnsAsync(new ResourceHistory { ResourceId = "doc-1" });

        var response = await Client(Admin).GetAsync("/api/v1/audit/resources/doc-1/history");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        _auditService.Verify(s => s.GetResourceHistoryAsync("doc-1", null), Times.Once);
    }

    [Fact]
    public async Task ResourceHistory_WithoutCallerHeader_IsUnauthorized()
    {
        var response = await Client(null).GetAsync("/api/v1/audit/resources/doc-1/history");

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    // POST /api/v1/audit/events

    [Fact]
    public async Task RecordEvent_StampsCallerAsActor()
    {
        _auditService
            .Setup(s => s.RecordEventAsync(It.IsAny<AuditEventRequest>()))
            .ReturnsAsync(Response("evt-new", Owner));

        var response = await Client(Owner).PostAsJsonAsync("/api/v1/audit/events", new
        {
            action = "create",
            resourceType = "document",
            resourceId = "doc-1",
        });

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        _auditService.Verify(s => s.RecordEventAsync(It.Is<AuditEventRequest>(r => r.UserId == Owner)), Times.Once);
    }

    [Fact]
    public async Task RecordEvent_ForgingAnotherActor_IsForbidden()
    {
        var response = await Client(Owner).PostAsJsonAsync("/api/v1/audit/events", new
        {
            userId = Other,
            action = "create",
            resourceType = "document",
            resourceId = "doc-1",
        });

        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        _auditService.Verify(s => s.RecordEventAsync(It.IsAny<AuditEventRequest>()), Times.Never);
    }

    [Fact]
    public async Task RecordEvent_AsServiceAccount_MayRecordOnBehalfOfAnotherUser()
    {
        _auditService
            .Setup(s => s.RecordEventAsync(It.IsAny<AuditEventRequest>()))
            .ReturnsAsync(Response("evt-new", Other));

        var response = await Client(ServiceAccount).PostAsJsonAsync("/api/v1/audit/events", new
        {
            userId = Other,
            action = "create",
            resourceType = "document",
            resourceId = "doc-1",
        });

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        _auditService.Verify(s => s.RecordEventAsync(It.Is<AuditEventRequest>(r => r.UserId == Other)), Times.Once);
    }

    [Fact]
    public async Task RecordEvent_WithoutCallerHeader_IsUnauthorized()
    {
        var response = await Client(null).PostAsJsonAsync("/api/v1/audit/events", new
        {
            action = "create",
            resourceType = "document",
            resourceId = "doc-1",
        });

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    // Cross-user endpoints: compliance report, export, archive

    [Theory]
    [InlineData("/api/v1/audit/reports/compliance")]
    [InlineData("/api/v1/audit/export")]
    public async Task CrossUserReads_AreForbiddenForUnprivilegedCallers(string path)
    {
        var response = await Client(Owner).GetAsync(path);

        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Theory]
    [InlineData("/api/v1/audit/reports/compliance")]
    [InlineData("/api/v1/audit/export")]
    public async Task CrossUserReads_RequireCallerHeader(string path)
    {
        var response = await Client(null).GetAsync(path);

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Fact]
    public async Task ComplianceReport_AsAdmin_IsAllowed()
    {
        _auditService
            .Setup(s => s.GetComplianceReportAsync("30d"))
            .ReturnsAsync(new ComplianceReport { Period = "30d" });

        var response = await Client(Admin).GetAsync("/api/v1/audit/reports/compliance");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task Export_AsAdmin_IsAllowed()
    {
        _auditService
            .Setup(s => s.ExportAsync(It.IsAny<DateTime>(), It.IsAny<DateTime>(), "json"))
            .ReturnsAsync(new ExportResult { Format = "json" });

        var response = await Client(Admin).GetAsync("/api/v1/audit/export");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task Archive_IsForbiddenForUnprivilegedCallers()
    {
        var response = await Client(Owner).PostAsync("/api/v1/audit/archive", null);

        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        _auditService.Verify(s => s.ArchiveOldEventsAsync(), Times.Never);
    }

    [Fact]
    public async Task Archive_RequiresCallerHeader()
    {
        var response = await Client(null).PostAsync("/api/v1/audit/archive", null);

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Fact]
    public async Task Archive_AsAdmin_IsAllowed()
    {
        _auditService.Setup(s => s.ArchiveOldEventsAsync()).ReturnsAsync(new ArchiveResult { ArchivedCount = 1 });

        var response = await Client(Admin).PostAsync("/api/v1/audit/archive", null);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    private static AuditEventResponse Response(string id, string userId) => new()
    {
        Id = id,
        UserId = userId,
        Action = "create",
        ResourceType = "document",
        ResourceId = "doc-1",
        Timestamp = DateTime.UtcNow,
    };
}

public class AuditApiFactory : WebApplicationFactory<Program>
{
    public Mock<IAuditService> AuditService { get; } = new();

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseSetting("Authorization:AdminUserIds:0", "admin-1");
        builder.UseSetting("Authorization:ServiceAccountIds:0", "svc-file-service");

        builder.ConfigureServices(services =>
        {
            services.RemoveAll<IAuditService>();
            services.AddSingleton(AuditService.Object);

            // The SNS/SQS consumer talks to AWS and is irrelevant to HTTP authorization.
            foreach (var hostedService in services.Where(d => d.ServiceType == typeof(IHostedService)).ToList())
            {
                services.Remove(hostedService);
            }
        });
    }
}
