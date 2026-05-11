using Amazon.DynamoDBv2;
using Amazon.S3;
using Amazon.SimpleNotificationService;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OtterWorks.FileService.Config;
using OtterWorks.FileService.Controllers;
using OtterWorks.FileService.Middleware;
using OtterWorks.FileService.Models;
using OtterWorks.FileService.Services;
using Prometheus;
using Serilog;
using Serilog.Formatting.Compact;

var builder = WebApplication.CreateBuilder(args);

// Structured logging with Serilog
Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .Enrich.WithProperty("service", "file-service")
    .Enrich.FromLogContext()
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
builder.Host.UseSerilog();

// Configuration
var awsSection = builder.Configuration.GetSection("Aws");
builder.Services.Configure<AwsSettings>(awsSection);
var awsSettings = awsSection.Get<AwsSettings>() ?? new AwsSettings();

// Bind environment variables
if (Environment.GetEnvironmentVariable("AWS_REGION") is { } region)
{
    awsSettings.Region = region;
}

if (Environment.GetEnvironmentVariable("AWS_ENDPOINT_URL") is { } endpointUrl)
{
    awsSettings.EndpointUrl = endpointUrl;
}

if (Environment.GetEnvironmentVariable("S3_BUCKET") is { } s3Bucket)
{
    awsSettings.S3Bucket = s3Bucket;
}

if (Environment.GetEnvironmentVariable("DYNAMODB_TABLE") is { } dynamoTable)
{
    awsSettings.DynamoDbTable = dynamoTable;
}

if (Environment.GetEnvironmentVariable("SNS_TOPIC_ARN") is { } snsArn)
{
    awsSettings.SnsTopicArn = snsArn;
}

if (Environment.GetEnvironmentVariable("MAX_UPLOAD_BYTES") is { } maxUpload && long.TryParse(maxUpload, out var maxBytes))
{
    awsSettings.MaxUploadBytes = maxBytes;
}

// Re-register as a configured instance
builder.Services.Configure<AwsSettings>(opts =>
{
    opts.Region = awsSettings.Region;
    opts.EndpointUrl = awsSettings.EndpointUrl;
    opts.S3Bucket = awsSettings.S3Bucket;
    opts.DynamoDbTable = awsSettings.DynamoDbTable;
    opts.DynamoDbFoldersTable = awsSettings.DynamoDbFoldersTable;
    opts.DynamoDbVersionsTable = awsSettings.DynamoDbVersionsTable;
    opts.DynamoDbSharesTable = awsSettings.DynamoDbSharesTable;
    opts.SnsTopicArn = awsSettings.SnsTopicArn;
    opts.MaxUploadBytes = awsSettings.MaxUploadBytes;
});

// AWS SDK clients
builder.Services.AddSingleton<IAmazonDynamoDB>(_ =>
{
    var config = new AmazonDynamoDBConfig { RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(awsSettings.Region) };
    if (!string.IsNullOrEmpty(awsSettings.EndpointUrl))
    {
        config.ServiceURL = awsSettings.EndpointUrl;
    }

    return new AmazonDynamoDBClient(config);
});

builder.Services.AddSingleton<IAmazonS3>(_ =>
{
    var config = new AmazonS3Config { RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(awsSettings.Region) };
    if (!string.IsNullOrEmpty(awsSettings.EndpointUrl))
    {
        config.ServiceURL = awsSettings.EndpointUrl;
        config.ForcePathStyle = true;
    }

    return new AmazonS3Client(config);
});

builder.Services.AddSingleton<IAmazonSimpleNotificationService>(_ =>
{
    var config = new AmazonSimpleNotificationServiceConfig { RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(awsSettings.Region) };
    if (!string.IsNullOrEmpty(awsSettings.EndpointUrl))
    {
        config.ServiceURL = awsSettings.EndpointUrl;
    }

    return new AmazonSimpleNotificationServiceClient(config);
});

// Application services
builder.Services.AddSingleton<IS3StorageService, S3StorageService>();
builder.Services.AddSingleton<IMetadataService, DynamoDbMetadataService>();
builder.Services.AddSingleton<IEventPublisher, SnsEventPublisher>();

// OpenTelemetry tracing
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing =>
    {
        tracing
            .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("file-service"))
            .AddAspNetCoreInstrumentation()
            .AddOtlpExporter();
    });

// Prometheus metrics
builder.Services.AddSingleton(Metrics.DefaultRegistry);

var app = builder.Build();

// Middleware pipeline
app.UseMiddleware<SecurityHeadersMiddleware>();
app.UseMiddleware<ErrorHandlingMiddleware>();
app.UseMiddleware<RequestLoggingMiddleware>();

// Prometheus metrics endpoint
app.UseHttpMetrics();

// Health check
app.MapGet("/health", () => Results.Ok(new HealthResponse()));

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

// Map file and folder API endpoints
app.MapFileEndpoints();

app.Run();

// Expose for integration test access
public partial class Program
{
}
