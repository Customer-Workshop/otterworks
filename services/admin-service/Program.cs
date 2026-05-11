using Microsoft.EntityFrameworkCore;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Middleware;
using OtterWorks.AdminService.Services;
using Prometheus;
using Serilog;
using Serilog.Formatting.Compact;

var builder = WebApplication.CreateBuilder(args);

// Structured logging with Serilog
Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .Enrich.WithProperty("service", "admin-service")
    .Enrich.FromLogContext()
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
builder.Host.UseSerilog();

// Database
var connectionString = builder.Configuration.GetConnectionString("DefaultConnection")
    ?? Environment.GetEnvironmentVariable("DATABASE_URL")
    ?? BuildConnectionString(builder.Configuration);

builder.Services.AddDbContext<AdminDbContext>(options =>
    options.UseNpgsql(connectionString));

// Services
builder.Services.AddScoped<IAuditLogger, AuditLogger>();
builder.Services.AddScoped<IBulkOperationsService, BulkOperationsService>();
builder.Services.AddScoped<IHealthChecker, HealthChecker>();
builder.Services.AddScoped<IMetricsAggregator, MetricsAggregator>();
builder.Services.AddHttpClient();

// OpenTelemetry
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing =>
    {
        tracing
            .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("admin-service"))
            .AddAspNetCoreInstrumentation()
            .AddOtlpExporter();
    });

// Prometheus
builder.Services.AddSingleton(Metrics.DefaultRegistry);

// Controllers
builder.Services.AddControllers();

// Swagger
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

// Middleware pipeline
app.UseMiddleware<SecurityHeadersMiddleware>();
app.UseMiddleware<ErrorHandlingMiddleware>();
app.UseMiddleware<JwtAuthMiddleware>();

// Prometheus metrics
app.UseHttpMetrics();

app.MapControllers();

// Prometheus metrics endpoint
app.MapGet("/metrics", async () =>
{
    using var stream = new MemoryStream();
    await Metrics.DefaultRegistry.CollectAndExportAsTextAsync(stream);
    stream.Position = 0;
    using var reader = new StreamReader(stream);
    var metricsText = await reader.ReadToEndAsync();
    return Results.Text(metricsText, "text/plain; version=0.0.4; charset=utf-8");
});

app.Run();

static string BuildConnectionString(IConfiguration config)
{
    var host = Environment.GetEnvironmentVariable("DATABASE_HOST")
        ?? Environment.GetEnvironmentVariable("POSTGRES_HOST")
        ?? config["Database:Host"] ?? "localhost";
    var port = Environment.GetEnvironmentVariable("DATABASE_PORT")
        ?? Environment.GetEnvironmentVariable("POSTGRES_PORT")
        ?? config["Database:Port"] ?? "5432";
    var user = Environment.GetEnvironmentVariable("DATABASE_USER")
        ?? Environment.GetEnvironmentVariable("POSTGRES_USER")
        ?? config["Database:User"] ?? "otterworks";
    var password = Environment.GetEnvironmentVariable("DATABASE_PASSWORD")
        ?? Environment.GetEnvironmentVariable("POSTGRES_PASSWORD")
        ?? config["Database:Password"] ?? "otterworks_dev";
    var database = Environment.GetEnvironmentVariable("DATABASE_NAME")
        ?? Environment.GetEnvironmentVariable("POSTGRES_DB")
        ?? config["Database:Name"] ?? "otterworks";

    return $"Host={host};Port={port};Username={user};Password={password};Database={database}";
}

public partial class Program
{
}
