using System.Text;
using System.Threading.Channels;
using Amazon.S3;
using FluentValidation;
using FluentValidation.AspNetCore;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.IdentityModel.Tokens;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OtterWorks.AnalyticsService.Config;
using OtterWorks.AnalyticsService.Middleware;
using OtterWorks.AnalyticsService.Models;
using OtterWorks.AnalyticsService.Services;
using OtterWorks.AnalyticsService.Workers;
using Prometheus;
using Serilog;
using Serilog.Formatting.Compact;
using StackExchange.Redis;

var builder = WebApplication.CreateBuilder(args);

// Structured logging with Serilog
Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .Enrich.WithProperty("service", "analytics-service")
    .Enrich.FromLogContext()
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
builder.Host.UseSerilog();

// Configuration from environment variables
builder.Services.Configure<AwsSettings>(builder.Configuration.GetSection("Aws"));
builder.Services.PostConfigure<AwsSettings>(opts =>
{
    opts.Region = Environment.GetEnvironmentVariable("AWS_REGION") ?? opts.Region;
    opts.EndpointUrl = Environment.GetEnvironmentVariable("AWS_ENDPOINT_URL") ?? opts.EndpointUrl;
    opts.DataLakeBucket = Environment.GetEnvironmentVariable("S3_DATA_LAKE_BUCKET") ?? opts.DataLakeBucket;
});
var awsSettings = builder.Configuration.GetSection("Aws").Get<AwsSettings>() ?? new AwsSettings();
awsSettings.Region = Environment.GetEnvironmentVariable("AWS_REGION") ?? awsSettings.Region;
awsSettings.EndpointUrl = Environment.GetEnvironmentVariable("AWS_ENDPOINT_URL") ?? awsSettings.EndpointUrl;

var postgresSettings = builder.Configuration.GetSection("Postgres").Get<PostgresSettings>() ?? new PostgresSettings();
postgresSettings.Host = Environment.GetEnvironmentVariable("POSTGRES_HOST") ?? postgresSettings.Host;
postgresSettings.Port = int.TryParse(Environment.GetEnvironmentVariable("POSTGRES_PORT"), out var pgPort) ? pgPort : postgresSettings.Port;
postgresSettings.User = Environment.GetEnvironmentVariable("POSTGRES_USER") ?? postgresSettings.User;
postgresSettings.Password = Environment.GetEnvironmentVariable("POSTGRES_PASSWORD") ?? postgresSettings.Password;
postgresSettings.Database = Environment.GetEnvironmentVariable("POSTGRES_DB") ?? postgresSettings.Database;

var redisSettings = builder.Configuration.GetSection("Redis").Get<RedisSettings>() ?? new RedisSettings();
redisSettings.Host = Environment.GetEnvironmentVariable("REDIS_HOST") ?? redisSettings.Host;
redisSettings.Port = int.TryParse(Environment.GetEnvironmentVariable("REDIS_PORT"), out var redisPort) ? redisPort : redisSettings.Port;

var jwtSecret = Environment.GetEnvironmentVariable("JWT_SECRET")
    ?? builder.Configuration.GetSection("Jwt").Get<JwtSettings>()?.Secret
    ?? "otterworks-local-dev-jwt-secret-change-me-in-production";

// AWS S3 client
builder.Services.AddSingleton<IAmazonS3>(_ =>
{
    var config = new AmazonS3Config
    {
        RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(awsSettings.Region),
    };
    if (!string.IsNullOrEmpty(awsSettings.EndpointUrl))
    {
        config.ServiceURL = awsSettings.EndpointUrl;
        config.ForcePathStyle = true;
    }

    return new AmazonS3Client(config);
});

// Redis
builder.Services.AddSingleton<IConnectionMultiplexer>(_ =>
{
    try
    {
        return ConnectionMultiplexer.Connect(redisSettings.ConnectionString);
    }
    catch (Exception ex)
    {
        Log.Warning(ex, "Redis connection failed");
        throw;
    }
});
builder.Services.AddSingleton<IRedisCacheService, RedisCacheService>();

// Services
builder.Services.AddSingleton<IMetricsRepository, InMemoryMetricsRepository>();
builder.Services.AddSingleton<IAnalyticsService, OtterWorks.AnalyticsService.Services.AnalyticsService>();
builder.Services.AddScoped<IDataLakeExporter, S3DataLakeExporter>();

// Channel<T> for background processing (Akka actors replacement)
builder.Services.AddSingleton(Channel.CreateUnbounded<AnalyticsEvent>());
builder.Services.AddHostedService<AggregationWorker>();
builder.Services.AddHostedService<DataLakeExportWorker>();

// FluentValidation
builder.Services.AddValidatorsFromAssemblyContaining<Program>();
builder.Services.AddFluentValidationAutoValidation();

// JWT authentication
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtSecret)),
            ValidateIssuer = false,
            ValidateAudience = false,
            ValidateLifetime = true,
            ClockSkew = TimeSpan.FromMinutes(5),
        };
    });
builder.Services.AddAuthorization();

// OpenTelemetry tracing
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing =>
    {
        tracing
            .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("analytics-service"))
            .AddAspNetCoreInstrumentation()
            .AddOtlpExporter();
    });

// Prometheus metrics
builder.Services.AddSingleton(Metrics.DefaultRegistry);

// Controllers & Swagger
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// Configure Kestrel to listen on port 8088
builder.WebHost.ConfigureKestrel(options =>
{
    options.ListenAnyIP(8088);
});

var app = builder.Build();

// Middleware pipeline
app.UseMiddleware<SecurityHeadersMiddleware>();
app.UseMiddleware<ErrorHandlingMiddleware>();
app.UseMiddleware<RequestLoggingMiddleware>();

// Swagger
app.UseSwagger();
app.UseSwaggerUI();

// Prometheus metrics endpoint
app.UseHttpMetrics();

// Authentication & Authorization
app.UseAuthentication();
app.UseAuthorization();

// Health check
app.MapGet("/health", () => Results.Ok(new
{
    status = "healthy",
    service = "analytics-service",
    version = "0.1.0",
}));

// Prometheus metrics
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

app.Run();

public partial class Program
{
}
