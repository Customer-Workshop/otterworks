using Amazon.S3;
using Amazon.SimpleNotificationService;
using Amazon.SQS;
using Microsoft.EntityFrameworkCore;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OtterWorks.ApiGateway.Config;
using OtterWorks.ApiGateway.Health;
using OtterWorks.ApiGateway.Middleware;
#pragma warning disable CA1852
using OtterWorks.ApiGateway.Proxy;
using Prometheus;
using Serilog;
using Serilog.Formatting.Compact;
using StackExchange.Redis;

var builder = WebApplication.CreateBuilder(args);

// Environment variable overrides
builder.Configuration.AddEnvironmentVariables();

// Structured logging with Serilog
Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .Enrich.WithProperty("service", "api-gateway")
    .Enrich.FromLogContext()
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
builder.Host.UseSerilog();

// Configuration binding
var gatewaySection = builder.Configuration.GetSection("Gateway");
builder.Services.Configure<GatewaySettings>(gatewaySection);
var gatewaySettings = gatewaySection.Get<GatewaySettings>() ?? new GatewaySettings();

var awsSection = builder.Configuration.GetSection("Aws");
builder.Services.Configure<AwsSettings>(awsSection);
var awsSettings = awsSection.Get<AwsSettings>() ?? new AwsSettings();

var routesSection = builder.Configuration.GetSection("ServiceRoutes");
builder.Services.Configure<ServiceRoutesSettings>(routesSection);
var serviceRoutes = routesSection.Get<ServiceRoutesSettings>() ?? new ServiceRoutesSettings();

// Apply environment variable overrides for service URLs
var envAuth = Environment.GetEnvironmentVariable("AUTH_SERVICE_URL");
if (!string.IsNullOrEmpty(envAuth))
{
    serviceRoutes.Auth = envAuth;
}

var envFile = Environment.GetEnvironmentVariable("FILE_SERVICE_URL");
if (!string.IsNullOrEmpty(envFile))
{
    serviceRoutes.File = envFile;
}

var envDoc = Environment.GetEnvironmentVariable("DOCUMENT_SERVICE_URL");
if (!string.IsNullOrEmpty(envDoc))
{
    serviceRoutes.Document = envDoc;
}

var envCollab = Environment.GetEnvironmentVariable("COLLAB_SERVICE_URL");
if (!string.IsNullOrEmpty(envCollab))
{
    serviceRoutes.Collab = envCollab;
}

var envNotif = Environment.GetEnvironmentVariable("NOTIFICATION_SERVICE_URL");
if (!string.IsNullOrEmpty(envNotif))
{
    serviceRoutes.Notification = envNotif;
}

var envSearch = Environment.GetEnvironmentVariable("SEARCH_SERVICE_URL");
if (!string.IsNullOrEmpty(envSearch))
{
    serviceRoutes.Search = envSearch;
}

var envAnalytics = Environment.GetEnvironmentVariable("ANALYTICS_SERVICE_URL");
if (!string.IsNullOrEmpty(envAnalytics))
{
    serviceRoutes.Analytics = envAnalytics;
}

var envAdmin = Environment.GetEnvironmentVariable("ADMIN_SERVICE_URL");
if (!string.IsNullOrEmpty(envAdmin))
{
    serviceRoutes.Admin = envAdmin;
}

var envAudit = Environment.GetEnvironmentVariable("AUDIT_SERVICE_URL");
if (!string.IsNullOrEmpty(envAudit))
{
    serviceRoutes.Audit = envAudit;
}

var envReport = Environment.GetEnvironmentVariable("REPORT_SERVICE_URL");
if (!string.IsNullOrEmpty(envReport))
{
    serviceRoutes.Report = envReport;
}

// AWS SDK clients
var awsRegion = Environment.GetEnvironmentVariable("AWS_REGION") ?? awsSettings.Region;
var awsEndpoint = Environment.GetEnvironmentVariable("AWS_ENDPOINT_URL") ?? awsSettings.EndpointUrl;

builder.Services.AddSingleton<IAmazonS3>(_ =>
{
    var config = new AmazonS3Config { RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(awsRegion) };
    if (!string.IsNullOrEmpty(awsEndpoint))
    {
        config.ServiceURL = awsEndpoint;
        config.ForcePathStyle = true;
    }

    return new AmazonS3Client(config);
});

builder.Services.AddSingleton<IAmazonSQS>(_ =>
{
    var config = new AmazonSQSConfig { RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(awsRegion) };
    if (!string.IsNullOrEmpty(awsEndpoint))
    {
        config.ServiceURL = awsEndpoint;
    }

    return new AmazonSQSClient(config);
});

builder.Services.AddSingleton<IAmazonSimpleNotificationService>(_ =>
{
    var config = new AmazonSimpleNotificationServiceConfig { RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(awsRegion) };
    if (!string.IsNullOrEmpty(awsEndpoint))
    {
        config.ServiceURL = awsEndpoint;
    }

    return new AmazonSimpleNotificationServiceClient(config);
});

// Redis
var redisHost = Environment.GetEnvironmentVariable("REDIS_HOST") ?? "localhost";
var redisPort = Environment.GetEnvironmentVariable("REDIS_PORT") ?? "6379";
builder.Services.AddSingleton<IConnectionMultiplexer>(_ =>
{
    var configOptions = ConfigurationOptions.Parse($"{redisHost}:{redisPort}");
    configOptions.AbortOnConnectFail = false;
    return ConnectionMultiplexer.Connect(configOptions);
});

// PostgreSQL via EF Core
var pgHost = Environment.GetEnvironmentVariable("POSTGRES_HOST") ?? "localhost";
var pgPort = Environment.GetEnvironmentVariable("POSTGRES_PORT") ?? "5432";
var pgUser = Environment.GetEnvironmentVariable("POSTGRES_USER") ?? "otterworks";
var pgPassword = Environment.GetEnvironmentVariable("POSTGRES_PASSWORD") ?? "otterworks";
var pgDb = Environment.GetEnvironmentVariable("POSTGRES_DB") ?? "otterworks";
var connectionString = $"Host={pgHost};Port={pgPort};Database={pgDb};Username={pgUser};Password={pgPassword}";
builder.Services.AddDbContext<GatewayDbContext>(options =>
    options.UseNpgsql(connectionString));

// Memory cache
builder.Services.AddMemoryCache();

// HTTP client for proxying
builder.Services.AddHttpClient("proxy")
    .ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler
    {
        AllowAutoRedirect = false,
    });

// Rate limiter
var rateLimiter = new RateLimiter(gatewaySettings.RateLimitRequestsPerSecond);
builder.Services.AddSingleton(rateLimiter);

// Circuit breaker
var cbConfig = new CircuitBreakerConfig
{
    MaxRequests = gatewaySettings.CircuitBreakerMaxRequests,
    Interval = TimeSpan.FromSeconds(gatewaySettings.CircuitBreakerIntervalSeconds),
    Timeout = TimeSpan.FromSeconds(gatewaySettings.CircuitBreakerTimeoutSeconds),
    FailureRatio = gatewaySettings.CircuitBreakerFailureRatio,
};
var cbManager = new CircuitBreakerManager(cbConfig);
builder.Services.AddSingleton(cbManager);

// Proxy routes
var routes = serviceRoutes.GetRouteMap()
    .Select(kvp => new ProxyRoute { Prefix = kvp.Key, TargetUrl = kvp.Value })
    .ToList();
builder.Services.AddSingleton<IEnumerable<ProxyRoute>>(routes);

// OpenTelemetry tracing
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing =>
    {
        tracing
            .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("api-gateway"))
            .AddAspNetCoreInstrumentation()
            .AddHttpClientInstrumentation()
            .AddOtlpExporter();
    });

// CORS
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy.WithOrigins(gatewaySettings.GetAllowedOrigins())
              .WithMethods(gatewaySettings.GetAllowedMethods())
              .WithHeaders(gatewaySettings.GetAllowedHeaders())
              .WithExposedHeaders("Link", "X-Request-ID")
              .AllowCredentials()
              .SetPreflightMaxAge(TimeSpan.FromSeconds(gatewaySettings.CorsMaxAgeSeconds));
    });
});

// Prometheus metrics
builder.Services.AddSingleton(Metrics.DefaultRegistry);

// Health checks
builder.Services.AddHealthChecks();

// Swagger
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

// Middleware pipeline (order matters)
app.UseMiddleware<ErrorHandlingMiddleware>();
app.UseMiddleware<RequestIdMiddleware>();
app.UseMiddleware<SecurityHeadersMiddleware>();
app.UseMiddleware<RequestLoggingMiddleware>();
app.UseMiddleware<RateLimitMiddleware>();
app.UseCors();
app.UseMiddleware<JwtAuthMiddleware>();

// Health endpoint
app.MapHealthEndpoints();

// Prometheus metrics endpoint
app.UseHttpMetrics();
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
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

// Reverse proxy for all service routes
app.UseMiddleware<ReverseProxyMiddleware>();

app.Run();


