using Amazon.DynamoDBv2;
using Amazon.SimpleNotificationService;
using Amazon.SQS;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OtterWorks.NotificationService.Config;
using OtterWorks.NotificationService.Controllers;
using OtterWorks.NotificationService.Middleware;
using OtterWorks.NotificationService.Models;
using OtterWorks.NotificationService.Services;
using Prometheus;
using Serilog;
using Serilog.Formatting.Compact;
using INotificationService = OtterWorks.NotificationService.Services.INotificationService;

var builder = WebApplication.CreateBuilder(args);

Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .Enrich.WithProperty("service", "notification-service")
    .Enrich.FromLogContext()
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
builder.Host.UseSerilog();

// Map flat docker-compose env vars to Aws config section
var envRegion = Environment.GetEnvironmentVariable("AWS_REGION");
var envEndpoint = Environment.GetEnvironmentVariable("AWS_ENDPOINT_URL");
var envSqsQueue = Environment.GetEnvironmentVariable("SQS_QUEUE_URL");
var envSnsTopic = Environment.GetEnvironmentVariable("SNS_TOPIC_ARN");
var envDynamoNotifications = Environment.GetEnvironmentVariable("DYNAMODB_TABLE_NOTIFICATIONS");
var envDynamoPreferences = Environment.GetEnvironmentVariable("DYNAMODB_TABLE_PREFERENCES");

if (envRegion is not null)
    builder.Configuration["Aws:Region"] = envRegion;
if (envEndpoint is not null)
    builder.Configuration["Aws:EndpointUrl"] = envEndpoint;
if (envSqsQueue is not null)
    builder.Configuration["Aws:SqsQueueUrl"] = envSqsQueue;
if (envSnsTopic is not null)
    builder.Configuration["Aws:SnsTopicArn"] = envSnsTopic;
if (envDynamoNotifications is not null)
    builder.Configuration["Aws:DynamoDbTableNotifications"] = envDynamoNotifications;
if (envDynamoPreferences is not null)
    builder.Configuration["Aws:DynamoDbTablePreferences"] = envDynamoPreferences;

var awsSection = builder.Configuration.GetSection("Aws");
builder.Services.Configure<AwsSettings>(awsSection);
var awsSettings = awsSection.Get<AwsSettings>() ?? new AwsSettings();

builder.Services.AddSingleton<IAmazonDynamoDB>(_ =>
{
    var config = new AmazonDynamoDBConfig { RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(awsSettings.Region) };
    if (!string.IsNullOrEmpty(awsSettings.EndpointUrl))
    {
        config.ServiceURL = awsSettings.EndpointUrl;
    }

    return new AmazonDynamoDBClient(config);
});

builder.Services.AddSingleton<IAmazonSQS>(_ =>
{
    var config = new AmazonSQSConfig { RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(awsSettings.Region) };
    if (!string.IsNullOrEmpty(awsSettings.EndpointUrl))
    {
        config.ServiceURL = awsSettings.EndpointUrl;
    }

    return new AmazonSQSClient(config);
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

builder.Services.AddSingleton<INotificationRepository, DynamoDbNotificationRepository>();
builder.Services.AddSingleton<INotificationService, OtterWorks.NotificationService.Services.NotificationService>();
builder.Services.AddHostedService<SqsConsumerService>();

builder.Services.AddOpenTelemetry()
    .WithTracing(tracing =>
    {
        tracing
            .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("notification-service"))
            .AddAspNetCoreInstrumentation()
            .AddOtlpExporter();
    });

builder.Services.AddSingleton(Metrics.DefaultRegistry);
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

app.UseMiddleware<SecurityHeadersMiddleware>();
app.UseMiddleware<ErrorHandlingMiddleware>();
app.UseHttpMetrics();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.MapGet("/health", () => Results.Ok(new HealthResponse()));

app.MapGet("/metrics", async () =>
{
    using var stream = new MemoryStream();
    await Metrics.DefaultRegistry.CollectAndExportAsTextAsync(stream);
    stream.Position = 0;
    using var reader = new StreamReader(stream);
    var metricsText = await reader.ReadToEndAsync();
    return Results.Text(metricsText, "text/plain; version=0.0.4; charset=utf-8");
});

app.MapNotificationEndpoints();

app.Run();
