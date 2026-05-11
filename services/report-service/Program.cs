using System.Threading.Channels;
using FluentValidation;
using Microsoft.EntityFrameworkCore;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OtterWorks.ReportService.Configuration;
using OtterWorks.ReportService.Data;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Services;
using Prometheus;
using QuestPDF.Infrastructure;
using Serilog;
using Serilog.Formatting.Compact;

QuestPDF.Settings.License = LicenseType.Community;

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
var reportSettingsSection = builder.Configuration.GetSection("ReportSettings");
builder.Services.Configure<ReportSettings>(reportSettingsSection);
var reportSettings = reportSettingsSection.Get<ReportSettings>() ?? new ReportSettings();

// Build connection string from env vars (matching Java application.properties pattern)
string dbHost = Environment.GetEnvironmentVariable("DB_HOST") ?? "localhost";
string dbPort = Environment.GetEnvironmentVariable("DB_PORT") ?? "5432";
string dbName = Environment.GetEnvironmentVariable("DB_NAME") ?? "otterworks_reports";
string dbUser = Environment.GetEnvironmentVariable("DB_USER") ?? "otterworks";
string dbPassword = Environment.GetEnvironmentVariable("DB_PASSWORD") ?? "otterworks_dev";
string connectionString = $"Host={dbHost};Port={dbPort};Database={dbName};Username={dbUser};Password={dbPassword}";

// EF Core with PostgreSQL
builder.Services.AddDbContext<ReportDbContext>(options =>
    options.UseNpgsql(connectionString));

// Repository
builder.Services.AddScoped<IReportRepository, ReportRepository>();

// Channel for async report generation
var channel = Channel.CreateUnbounded<long>();
builder.Services.AddSingleton(channel);

// Services
builder.Services.AddScoped<IReportService, OtterWorks.ReportService.Services.ReportService>();
builder.Services.AddScoped<IReportDataFetcher, ReportDataFetcher>();
builder.Services.AddScoped<IPdfReportGenerator, PdfReportGenerator>();
builder.Services.AddScoped<ICsvReportGenerator, CsvReportGenerator>();
builder.Services.AddScoped<IExcelReportGenerator, ExcelReportGenerator>();

// Background worker
builder.Services.AddHostedService<ReportGenerationWorker>();

// HTTP clients with timeouts
builder.Services.AddHttpClient("analytics", client =>
{
    client.BaseAddress = new Uri(reportSettings.AnalyticsServiceUrl);
    client.Timeout = TimeSpan.FromMilliseconds(reportSettings.ReadTimeoutMs);
});
builder.Services.AddHttpClient("audit", client =>
{
    client.BaseAddress = new Uri(reportSettings.AuditServiceUrl);
    client.Timeout = TimeSpan.FromMilliseconds(reportSettings.ReadTimeoutMs);
});
builder.Services.AddHttpClient("auth", client =>
{
    client.BaseAddress = new Uri(reportSettings.AuthServiceUrl);
    client.Timeout = TimeSpan.FromMilliseconds(reportSettings.ReadTimeoutMs);
});

// Memory cache
builder.Services.AddMemoryCache();

// FluentValidation
builder.Services.AddValidatorsFromAssemblyContaining<ReportRequestValidator>();

// Swagger
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// Controllers
builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.Converters.Add(new System.Text.Json.Serialization.JsonStringEnumConverter());
    });

// OpenTelemetry tracing
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing =>
    {
        tracing
            .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("report-service"))
            .AddAspNetCoreInstrumentation()
            .AddOtlpExporter();
    });

// Prometheus metrics
builder.Services.AddSingleton(Metrics.DefaultRegistry);

// Health checks
builder.Services.AddHealthChecks();

// CORS
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy.AllowAnyOrigin().AllowAnyMethod().AllowAnyHeader();
    });
});

var app = builder.Build();

// Apply migrations / ensure DB created
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<ReportDbContext>();
    db.Database.EnsureCreated();
}

// Ensure output directory exists
Directory.CreateDirectory(reportSettings.OutputDir);

// Security headers
app.Use(async (context, next) =>
{
    context.Response.Headers["X-Frame-Options"] = "DENY";
    context.Response.Headers["X-Content-Type-Options"] = "nosniff";
    context.Response.Headers["X-XSS-Protection"] = "1; mode=block";
    await next();
});

app.UseCors();

// Swagger
app.UseSwagger();
app.UseSwaggerUI();

// Prometheus metrics
app.UseHttpMetrics();
app.MapGet("/metrics", async () =>
{
    using var stream = new MemoryStream();
    await Metrics.DefaultRegistry.CollectAndExportAsTextAsync(stream);
    stream.Position = 0;
    using var reader = new StreamReader(stream);
    string metricsText = await reader.ReadToEndAsync();
    return Results.Text(metricsText, "text/plain; version=0.0.4; charset=utf-8");
});

app.MapControllers();

app.Run();

public partial class Program
{
}
