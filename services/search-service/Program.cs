using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OtterWorks.SearchService.Configuration;
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

// Configuration binding
var serviceSection = builder.Configuration.GetSection("SearchService");
builder.Services.Configure<SearchServiceSettings>(serviceSection);
builder.Services.Configure<MeiliSearchSettings>(builder.Configuration.GetSection("SearchService:MeiliSearch"));
builder.Services.Configure<SqsSettings>(builder.Configuration.GetSection("SearchService:Sqs"));
builder.Services.Configure<AuthSettings>(builder.Configuration.GetSection("SearchService:Auth"));

var settings = serviceSection.Get<SearchServiceSettings>() ?? new SearchServiceSettings();

// Override settings from environment variables
string? meiliUrl = Environment.GetEnvironmentVariable("MEILISEARCH_URL");
if (!string.IsNullOrEmpty(meiliUrl))
{
    builder.Services.PostConfigure<MeiliSearchSettings>(s => s.Url = meiliUrl);
}

string? meiliApiKey = Environment.GetEnvironmentVariable("MEILISEARCH_API_KEY");
if (!string.IsNullOrEmpty(meiliApiKey))
{
    builder.Services.PostConfigure<MeiliSearchSettings>(s => s.ApiKey = meiliApiKey);
}

string? sqsEnabled = Environment.GetEnvironmentVariable("SQS_ENABLED");
if (!string.IsNullOrEmpty(sqsEnabled))
{
    builder.Services.PostConfigure<SqsSettings>(s => s.Enabled = sqsEnabled.Equals("true", StringComparison.OrdinalIgnoreCase));
}

string? sqsQueueUrl = Environment.GetEnvironmentVariable("SQS_QUEUE_URL");
if (!string.IsNullOrEmpty(sqsQueueUrl))
{
    builder.Services.PostConfigure<SqsSettings>(s => s.QueueUrl = sqsQueueUrl);
}

string? awsRegion = Environment.GetEnvironmentVariable("AWS_REGION");
if (!string.IsNullOrEmpty(awsRegion))
{
    builder.Services.PostConfigure<SqsSettings>(s => s.Region = awsRegion);
}

string? awsEndpoint = Environment.GetEnvironmentVariable("AWS_ENDPOINT_URL");
if (!string.IsNullOrEmpty(awsEndpoint))
{
    builder.Services.PostConfigure<SqsSettings>(s => s.EndpointUrl = awsEndpoint);
}

string? requireAuth = Environment.GetEnvironmentVariable("REQUIRE_AUTH");
if (!string.IsNullOrEmpty(requireAuth))
{
    builder.Services.PostConfigure<AuthSettings>(s => s.RequireAuth = requireAuth.Equals("true", StringComparison.OrdinalIgnoreCase));
}

string? serviceToken = Environment.GetEnvironmentVariable("SEARCH_SERVICE_TOKEN");
if (!string.IsNullOrEmpty(serviceToken))
{
    builder.Services.PostConfigure<AuthSettings>(s => s.ServiceToken = serviceToken);
}

// Service registration
builder.Services.AddSingleton<ISearchAnalyticsTracker, SearchAnalyticsTracker>();
builder.Services.AddSingleton<IMeiliSearchService, MeiliSearchClientService>();
builder.Services.AddScoped<IIndexerService, IndexerService>();
builder.Services.AddHttpClient("DocumentService", c => c.Timeout = TimeSpan.FromSeconds(30));
builder.Services.AddHttpClient("FileService", c => c.Timeout = TimeSpan.FromSeconds(30));

// SQS consumer background service
builder.Services.AddHostedService<SqsConsumerService>();

// Controllers
builder.Services.AddControllers();

// Swagger/OpenAPI
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(c =>
{
    c.SwaggerDoc("v1", new Microsoft.OpenApi.Models.OpenApiInfo
    {
        Title = "OtterWorks Search Service",
        Version = "v1",
        Description = "Full-text search and indexing service for OtterWorks platform",
    });
});

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

// Health checks
builder.Services.AddHealthChecks();

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

// Port binding (must be before Build())
int port = settings.Port;
string? portEnv = Environment.GetEnvironmentVariable("PORT");
if (!string.IsNullOrEmpty(portEnv) && int.TryParse(portEnv, out var envPort))
    port = envPort;
builder.WebHost.UseUrls($"http://0.0.0.0:{port}");

var app = builder.Build();

// Security headers
app.Use(async (context, next) =>
{
    context.Response.Headers["X-Frame-Options"] = "DENY";
    context.Response.Headers["X-Content-Type-Options"] = "nosniff";
    context.Response.Headers["X-XSS-Protection"] = "1; mode=block";
    await next();
});

// CORS
app.UseCors();

// Auth middleware
app.UseMiddleware<AuthMiddleware>();

// Swagger
app.UseSwagger();
app.UseSwaggerUI();

// Prometheus metrics
app.UseHttpMetrics();

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

// Map controllers
app.MapControllers();

// Initialize MeiliSearch indices
try
{
    var searchService = app.Services.GetRequiredService<IMeiliSearchService>();
    await searchService.EnsureIndicesAsync();
    Log.Information("MeiliSearch indices ensured");
}
catch (Exception ex)
{
    Log.Warning(ex, "MeiliSearch indices creation deferred: MeiliSearch not available");
}

app.Run();

public partial class Program
{
}
