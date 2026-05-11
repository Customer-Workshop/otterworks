using Amazon.SQS;
using Microsoft.EntityFrameworkCore;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OtterWorks.SearchService.Config;
using OtterWorks.SearchService.Controllers;
using OtterWorks.SearchService.Middleware;
using OtterWorks.SearchService.Services;
using Prometheus;
using Serilog;
using Serilog.Formatting.Compact;

var builder = WebApplication.CreateBuilder(args);

// Structured logging with Serilog
Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .Enrich.WithProperty("service", "search-service")
    .Enrich.FromLogContext()
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
builder.Host.UseSerilog();

// Override configuration from environment variables (docker-compose)
builder.Services.Configure<MeilisearchSettings>(opts =>
{
    builder.Configuration.GetSection("Meilisearch").Bind(opts);
    var url = Environment.GetEnvironmentVariable("MEILISEARCH_URL");
    if (!string.IsNullOrEmpty(url))
    {
        opts.Url = url;
    }
});

builder.Services.Configure<SqsSettings>(opts =>
{
    builder.Configuration.GetSection("Sqs").Bind(opts);
    var enabled = Environment.GetEnvironmentVariable("SQS_ENABLED");
    if (!string.IsNullOrEmpty(enabled))
    {
        opts.Enabled = string.Equals(enabled, "true", StringComparison.OrdinalIgnoreCase);
    }

    var queueUrl = Environment.GetEnvironmentVariable("SQS_QUEUE_URL");
    if (!string.IsNullOrEmpty(queueUrl))
    {
        opts.QueueUrl = queueUrl;
    }

    var region = Environment.GetEnvironmentVariable("AWS_REGION");
    if (!string.IsNullOrEmpty(region))
    {
        opts.Region = region;
    }

    var endpoint = Environment.GetEnvironmentVariable("AWS_ENDPOINT_URL");
    if (!string.IsNullOrEmpty(endpoint))
    {
        opts.EndpointUrl = endpoint;
    }
});

builder.Services.Configure<AuthSettings>(opts =>
{
    builder.Configuration.GetSection("Auth").Bind(opts);
    var jwtSecret = Environment.GetEnvironmentVariable("JWT_SECRET");
    if (!string.IsNullOrEmpty(jwtSecret))
    {
        opts.ServiceToken = jwtSecret;
    }
});

var meilisearchUrl = Environment.GetEnvironmentVariable("MEILISEARCH_URL")
    ?? builder.Configuration.GetSection("Meilisearch")["Url"]
    ?? "http://localhost:7700";
var meilisearchApiKey = builder.Configuration.GetSection("Meilisearch")["ApiKey"] ?? string.Empty;

var sqsEnabled = string.Equals(
    Environment.GetEnvironmentVariable("SQS_ENABLED") ?? builder.Configuration.GetSection("Sqs")["Enabled"],
    "true",
    StringComparison.OrdinalIgnoreCase);
var sqsRegion = Environment.GetEnvironmentVariable("AWS_REGION") ?? builder.Configuration.GetSection("Sqs")["Region"] ?? "us-east-1";
var sqsEndpoint = Environment.GetEnvironmentVariable("AWS_ENDPOINT_URL") ?? builder.Configuration.GetSection("Sqs")["EndpointUrl"];

// Analytics singleton (persists across transient MeilisearchService instances)
builder.Services.AddSingleton<OtterWorks.SearchService.Services.SearchAnalyticsStore>();

// Meilisearch HTTP client
builder.Services.AddHttpClient<IMeilisearchService, MeilisearchService>(client =>
{
    client.BaseAddress = new Uri(meilisearchUrl);
    if (!string.IsNullOrEmpty(meilisearchApiKey))
    {
        client.DefaultRequestHeaders.Add("Authorization", $"Bearer {meilisearchApiKey}");
    }
});

// PostgreSQL via EF Core
var pgHost = Environment.GetEnvironmentVariable("POSTGRES_HOST") ?? "localhost";
var pgPort = Environment.GetEnvironmentVariable("POSTGRES_PORT") ?? "5432";
var pgUser = Environment.GetEnvironmentVariable("POSTGRES_USER") ?? "otterworks";
var pgPass = Environment.GetEnvironmentVariable("POSTGRES_PASSWORD") ?? "otterworks_dev";
var pgDb = Environment.GetEnvironmentVariable("POSTGRES_DB") ?? "otterworks";
var connectionString = builder.Configuration.GetConnectionString("Postgres")
    ?? $"Host={pgHost};Port={pgPort};Database={pgDb};Username={pgUser};Password={pgPass}";
builder.Services.AddDbContext<SearchDbContext>(options =>
    options.UseNpgsql(connectionString));

// Redis
var redisHost = Environment.GetEnvironmentVariable("REDIS_HOST") ?? builder.Configuration["REDIS_HOST"] ?? "localhost";
var redisPort = Environment.GetEnvironmentVariable("REDIS_PORT") ?? builder.Configuration["REDIS_PORT"] ?? "6379";
builder.Services.AddSingleton<StackExchange.Redis.IConnectionMultiplexer>(sp =>
{
    try
    {
        return StackExchange.Redis.ConnectionMultiplexer.Connect($"{redisHost}:{redisPort},abortConnect=false,connectTimeout=5000");
    }
    catch (Exception ex)
    {
        Log.Warning(ex, "Redis connection failed, using null multiplexer");
        return StackExchange.Redis.ConnectionMultiplexer.Connect("localhost:6379,abortConnect=false,connectTimeout=1000");
    }
});

// AWS SQS
builder.Services.AddSingleton<IAmazonSQS>(_ =>
{
    var config = new AmazonSQSConfig { RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(sqsRegion) };
    if (!string.IsNullOrEmpty(sqsEndpoint))
    {
        config.ServiceURL = sqsEndpoint;
    }

    return new AmazonSQSClient(config);
});

// Indexer service
builder.Services.AddHttpClient();
builder.Services.AddScoped<IIndexer, Indexer>();

// SQS consumer background service
if (sqsEnabled)
{
    builder.Services.AddHostedService<OtterWorks.SearchService.Services.SqsConsumer>();
}

// OpenTelemetry tracing
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing =>
    {
        tracing
            .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("search-service"))
            .AddAspNetCoreInstrumentation()
            .AddOtlpExporter();
    });

// Prometheus metrics
builder.Services.AddSingleton(Metrics.DefaultRegistry);

// CORS
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy.WithOrigins("http://localhost:3000", "http://localhost:4200")
            .AllowAnyHeader()
            .AllowAnyMethod();
    });
});

// Swagger
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

// Middleware pipeline
app.UseMiddleware<SecurityHeadersMiddleware>();
app.UseMiddleware<ErrorHandlingMiddleware>();
app.UseMiddleware<RequestLoggingMiddleware>();
app.UseMiddleware<AuthMiddleware>();
app.UseCors();

// Prometheus metrics
app.UseHttpMetrics();

// Swagger
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

// Health endpoint
app.MapGet("/health", () => Results.Json(new
{
    status = "healthy",
    service = "search-service",
    version = "0.1.0",
}));

// Readiness endpoint
app.MapGet("/health/ready", async (IMeilisearchService searchService) =>
{
    var healthy = await searchService.PingAsync();
    if (healthy)
    {
        return Results.Json(new { ready = true });
    }

    return Results.Json(new { ready = false, reason = "meilisearch_unavailable" }, statusCode: 503);
});

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

// Search endpoints
app.MapSearchEndpoints();

// Ensure indices on startup
try
{
    using var scope = app.Services.CreateScope();
    var searchService = scope.ServiceProvider.GetRequiredService<IMeilisearchService>();
    await searchService.EnsureIndicesAsync();
    Log.Information("Meilisearch indices ensured");
}
catch (Exception ex)
{
    Log.Warning(ex, "Meilisearch indices creation deferred");
}

app.Run();

// Needed for integration test WebApplicationFactory
public partial class Program
{
}
