using FluentValidation;
using Microsoft.EntityFrameworkCore;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OtterWorks.ReportService.Config;
using OtterWorks.ReportService.Data;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Repositories;
using OtterWorks.ReportService.Services;
using Prometheus;
using Serilog;
using Serilog.Formatting.Compact;

var builder = WebApplication.CreateBuilder(args);

// Structured logging with Serilog
Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .Enrich.WithProperty("service", "report-service")
    .Enrich.FromLogContext()
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
builder.Host.UseSerilog();

// Configuration
var serviceUrlsSection = builder.Configuration.GetSection("ServiceUrls");
builder.Services.Configure<ServiceUrlsSettings>(serviceUrlsSection);

var reportSettingsSection = builder.Configuration.GetSection("ReportSettings");
builder.Services.Configure<ReportSettings>(reportSettingsSection);
var reportOutputDir = Environment.GetEnvironmentVariable("REPORT_OUTPUT_DIR");
if (!string.IsNullOrEmpty(reportOutputDir))
{
    builder.Services.PostConfigure<ReportSettings>(s => s.OutputDir = reportOutputDir);
}
var reportSettings = reportSettingsSection.Get<ReportSettings>() ?? new ReportSettings();
reportSettings.OutputDir = reportOutputDir ?? reportSettings.OutputDir;

// Resolve connection string with environment variable substitution
var rawConnectionString = builder.Configuration.GetConnectionString("ReportsDb") ?? "";
var connectionString = Environment.ExpandEnvironmentVariables(rawConnectionString)
    .Replace("${DB_HOST}", Environment.GetEnvironmentVariable("DB_HOST") ?? "localhost")
    .Replace("${DB_PORT}", Environment.GetEnvironmentVariable("DB_PORT") ?? "5432")
    .Replace("${DB_NAME}", Environment.GetEnvironmentVariable("DB_NAME") ?? "otterworks_reports")
    .Replace("${DB_USER}", Environment.GetEnvironmentVariable("DB_USER") ?? "otterworks")
    .Replace("${DB_PASSWORD}", Environment.GetEnvironmentVariable("DB_PASSWORD") ?? "otterworks_dev");

// Database
builder.Services.AddDbContext<ReportDbContext>(options =>
    options.UseNpgsql(connectionString));

// HttpClientFactory with named clients
var serviceUrls = serviceUrlsSection.Get<ServiceUrlsSettings>() ?? new ServiceUrlsSettings();

// Resolve service URLs from environment variables
var analyticsUrl = Environment.GetEnvironmentVariable("ANALYTICS_SERVICE_URL") ?? serviceUrls.Analytics;
var auditUrl = Environment.GetEnvironmentVariable("AUDIT_SERVICE_URL") ?? serviceUrls.Audit;
var authUrl = Environment.GetEnvironmentVariable("AUTH_SERVICE_URL") ?? serviceUrls.Auth;

builder.Services.AddHttpClient("analytics", client =>
{
    client.BaseAddress = new Uri(analyticsUrl);
    client.Timeout = TimeSpan.FromMilliseconds(reportSettings.ReadTimeoutMs);
});
builder.Services.AddHttpClient("audit", client =>
{
    client.BaseAddress = new Uri(auditUrl);
    client.Timeout = TimeSpan.FromMilliseconds(reportSettings.ReadTimeoutMs);
});
builder.Services.AddHttpClient("auth", client =>
{
    client.BaseAddress = new Uri(authUrl);
    client.Timeout = TimeSpan.FromMilliseconds(reportSettings.ReadTimeoutMs);
});

// Memory cache
builder.Services.AddMemoryCache();

// Application services
builder.Services.AddScoped<IReportRepository, ReportRepository>();
builder.Services.AddScoped<IReportDataFetcher, ReportDataFetcher>();
builder.Services.AddScoped<IPdfReportGenerator, PdfReportGenerator>();
builder.Services.AddScoped<ICsvReportGenerator, CsvReportGenerator>();
builder.Services.AddScoped<IExcelReportGenerator, ExcelReportGenerator>();
builder.Services.AddScoped<IReportService, OtterWorks.ReportService.Services.ReportService>();
builder.Services.AddSingleton<ReportGenerationWorker>();
builder.Services.AddSingleton<IReportGenerationWorker>(sp => sp.GetRequiredService<ReportGenerationWorker>());
builder.Services.AddHostedService(sp => sp.GetRequiredService<ReportGenerationWorker>());

// FluentValidation
builder.Services.AddValidatorsFromAssemblyContaining<ReportRequestValidator>();

// OpenTelemetry tracing
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing =>
    {
        tracing
            .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("report-service"))
            .AddAspNetCoreInstrumentation()
            .AddOtlpExporter();
    });

// Health checks
builder.Services.AddHealthChecks();

// Prometheus metrics
builder.Services.AddSingleton(Metrics.DefaultRegistry);

// Swagger
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// Controllers
builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.Converters.Add(new System.Text.Json.Serialization.JsonStringEnumConverter());
    });

var app = builder.Build();

// Auto-migrate database
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<ReportDbContext>();
    try
    {
        db.Database.EnsureCreated();
    }
    catch (Exception ex)
    {
        Log.Warning(ex, "Database migration failed — will retry on first request");
    }
}

// Ensure report output directory exists
Directory.CreateDirectory(reportSettings.OutputDir);

// Prometheus metrics
app.UseHttpMetrics();

// Health check
app.MapGet("/health", () => Results.Ok(new
{
    status = "healthy",
    service = "report-service",
    version = "0.1.0"
}));

// Metrics endpoint
app.MapGet("/metrics", async () =>
{
    using var stream = new MemoryStream();
    await Metrics.DefaultRegistry.CollectAndExportAsTextAsync(stream);
    stream.Position = 0;
    using var reader = new StreamReader(stream);
    var metricsText = await reader.ReadToEndAsync();
    return Results.Text(metricsText, "text/plain; version=0.0.4; charset=utf-8");
});

// Swagger
app.UseSwagger();
app.UseSwaggerUI();

app.MapControllers();

app.Run();

public partial class Program { }
