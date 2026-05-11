using Amazon.SimpleNotificationService;
using FluentValidation;
using FluentValidation.AspNetCore;
using Microsoft.EntityFrameworkCore;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OtterWorks.DocumentService.Config;
using OtterWorks.DocumentService.Data;
using OtterWorks.DocumentService.Middleware;
using OtterWorks.DocumentService.Services;
using OtterWorks.DocumentService.Validators;
using Prometheus;
using Serilog;
using Serilog.Formatting.Compact;

var builder = WebApplication.CreateBuilder(args);

// Structured logging with Serilog
Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .Enrich.WithProperty("service", "document-service")
    .Enrich.FromLogContext()
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
builder.Host.UseSerilog();

// Configuration
var awsSection = builder.Configuration.GetSection("Aws");
builder.Services.Configure<AwsSettings>(awsSection);
var awsSettings = awsSection.Get<AwsSettings>() ?? new AwsSettings();

var redisSection = builder.Configuration.GetSection("Redis");
builder.Services.Configure<RedisSettings>(redisSection);

var jwtSection = builder.Configuration.GetSection("Jwt");
builder.Services.Configure<JwtSettings>(jwtSection);

// PostgreSQL with EF Core
var connectionString = builder.Configuration.GetConnectionString("DefaultConnection");
builder.Services.AddDbContext<DocumentDbContext>(options =>
    options.UseNpgsql(connectionString));

// AWS SNS client
builder.Services.AddSingleton<IAmazonSimpleNotificationService>(_ =>
{
    var config = new AmazonSimpleNotificationServiceConfig
    {
        RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(awsSettings.Region),
    };
    if (!string.IsNullOrEmpty(awsSettings.EndpointUrl))
    {
        config.ServiceURL = awsSettings.EndpointUrl;
    }

    return new AmazonSimpleNotificationServiceClient(config);
});

// Redis
var redisSettings = redisSection.Get<RedisSettings>() ?? new RedisSettings();
builder.Services.AddSingleton<StackExchange.Redis.IConnectionMultiplexer>(sp =>
{
    return StackExchange.Redis.ConnectionMultiplexer.Connect(redisSettings.ConnectionString);
});

// Services
builder.Services.AddScoped<IEventPublisher, SnsEventPublisher>();
builder.Services.AddScoped<IDocumentService, OtterWorks.DocumentService.Services.DocumentService>();

// Validators
builder.Services.AddFluentValidationAutoValidation();
builder.Services.AddValidatorsFromAssemblyContaining<DocumentCreateRequestValidator>();

// Controllers
builder.Services.AddControllers();

// Swagger
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// CORS
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy.WithOrigins("http://localhost:3000", "http://localhost:4200")
            .AllowAnyMethod()
            .AllowAnyHeader()
            .AllowCredentials();
    });
});

// OpenTelemetry tracing
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing =>
    {
        tracing
            .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("document-service"))
            .AddAspNetCoreInstrumentation()
            .AddOtlpExporter();
    });

// Prometheus metrics
builder.Services.AddSingleton(Metrics.DefaultRegistry);

// Memory cache
builder.Services.AddMemoryCache();

var app = builder.Build();

// Ensure database is created
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<DocumentDbContext>();
    await db.Database.EnsureCreatedAsync();
}

// Middleware pipeline
app.UseMiddleware<ErrorHandlingMiddleware>();
app.UseMiddleware<SecurityHeadersMiddleware>();
app.UseMiddleware<RequestLoggingMiddleware>();

app.UseCors();

// Swagger
app.UseSwagger();
app.UseSwaggerUI();

// Prometheus metrics
app.UseHttpMetrics();

// Health check
app.MapGet("/health", () => Results.Ok(new
{
    status = "healthy",
    service = "document-service",
    version = "0.1.0",
}));

// Metrics
app.MapGet("/metrics", async () =>
{
    using var stream = new MemoryStream();
    await Metrics.DefaultRegistry.CollectAndExportAsTextAsync(stream);
    stream.Position = 0;
    using var reader = new StreamReader(stream);
    var metricsText = await reader.ReadToEndAsync();
    return Results.Text(metricsText, "text/plain; version=0.0.4; charset=utf-8");
});

app.MapControllers();

app.Run();

public partial class Program
{
}
