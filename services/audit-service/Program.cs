using OtterWorks.AuditService.Config;
using OtterWorks.AuditService.Services;
using Serilog;
using Serilog.Formatting.Compact;

var builder = WebApplication.CreateBuilder(args);

// Structured logging with Serilog
Log.Logger = new LoggerConfiguration()
    .Enrich.WithProperty("service", "audit-service")
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
builder.Host.UseSerilog();

// Configuration
builder.Services.Configure<AwsSettings>(builder.Configuration.GetSection("Aws"));
builder.Services.AddSingleton<IAuditRepository, DynamoDbAuditRepository>();
builder.Services.AddSingleton<IAuditArchiver, S3AuditArchiver>();
builder.Services.AddMediatR(cfg => cfg.RegisterServicesFromAssembly(typeof(Program).Assembly));

// Prometheus metrics
builder.Services.AddHealthChecks();

var app = builder.Build();

// Health check
app.MapGet("/health", () => Results.Ok(new { status = "healthy", service = "audit-service" }));

// Metrics
app.MapGet("/metrics", () =>
{
    return Results.Text(
        "# HELP audit_service_up Audit Service is running\n# TYPE audit_service_up gauge\naudit_service_up 1\n",
        "text/plain"
    );
});

// Audit API endpoints
app.MapPost("/api/v1/audit/events", async (AuditEventRequest request, IAuditRepository repo) =>
{
    var auditEvent = new AuditEvent
    {
        Id = Guid.NewGuid().ToString(),
        UserId = request.UserId,
        Action = request.Action,
        ResourceType = request.ResourceType,
        ResourceId = request.ResourceId,
        Details = request.Details,
        IpAddress = request.IpAddress,
        UserAgent = request.UserAgent,
        Timestamp = DateTime.UtcNow,
    };

    await repo.SaveEventAsync(auditEvent);
    Log.Information("Audit event recorded: {Action} on {ResourceType}/{ResourceId}", request.Action, request.ResourceType, request.ResourceId);
    return Results.Created($"/api/v1/audit/events/{auditEvent.Id}", auditEvent);
});

app.MapGet("/api/v1/audit/events", async (string? userId, string? action, string? resourceType, int page = 1, int pageSize = 20, IAuditRepository repo) =>
{
    var events = await repo.QueryEventsAsync(userId, action, resourceType, page, pageSize);
    return Results.Ok(events);
});

app.MapGet("/api/v1/audit/events/{id}", async (string id, IAuditRepository repo) =>
{
    var auditEvent = await repo.GetEventAsync(id);
    return auditEvent is not null ? Results.Ok(auditEvent) : Results.NotFound();
});

app.MapPost("/api/v1/audit/export", async (ExportRequest request, IAuditArchiver archiver) =>
{
    var exportUrl = await archiver.ExportToS3Async(request.StartDate, request.EndDate, request.UserId);
    return Results.Ok(new { exportUrl });
});

app.MapGet("/api/v1/audit/compliance/gdpr/{userId}", async (string userId, IAuditRepository repo) =>
{
    var events = await repo.GetAllUserEventsAsync(userId);
    return Results.Ok(new { userId, eventCount = events.Count, events });
});

app.Run();

// Request/Response records
public record AuditEventRequest(string UserId, string Action, string ResourceType, string ResourceId, Dictionary<string, string>? Details, string? IpAddress, string? UserAgent);
public record ExportRequest(DateTime StartDate, DateTime EndDate, string? UserId);
