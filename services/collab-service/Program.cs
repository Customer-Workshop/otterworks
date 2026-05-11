using System.Text;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OtterWorks.CollabService.Config;
using OtterWorks.CollabService.Controllers;
using OtterWorks.CollabService.Hubs;
using OtterWorks.CollabService.Middleware;
using OtterWorks.CollabService.Services;
using Prometheus;
using Serilog;
using Serilog.Formatting.Compact;

var builder = WebApplication.CreateBuilder(args);

// Structured logging with Serilog
Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .Enrich.WithProperty("service", "collab-service")
    .Enrich.FromLogContext()
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
builder.Host.UseSerilog();

// Configuration from environment variables and appsettings
var redisSettings = new RedisSettings();
builder.Configuration.GetSection("Redis").Bind(redisSettings);
redisSettings.Host = Environment.GetEnvironmentVariable("REDIS_HOST") ?? redisSettings.Host;
if (int.TryParse(Environment.GetEnvironmentVariable("REDIS_PORT"), out int redisPort))
{
    redisSettings.Port = redisPort;
}

redisSettings.Password = Environment.GetEnvironmentVariable("REDIS_PASSWORD") ?? redisSettings.Password;

var jwtSettings = new JwtSettings();
builder.Configuration.GetSection("Jwt").Bind(jwtSettings);
jwtSettings.Secret = Environment.GetEnvironmentVariable("JWT_SECRET") ?? jwtSettings.Secret;

var persistenceSettings = new PersistenceSettings();
builder.Configuration.GetSection("Persistence").Bind(persistenceSettings);

var corsSettings = new CorsSettings();
builder.Configuration.GetSection("Cors").Bind(corsSettings);
string corsOrigins = Environment.GetEnvironmentVariable("CORS_ORIGINS") ?? corsSettings.Origins;
corsSettings.Origins = corsOrigins;

string httpPort = Environment.GetEnvironmentVariable("HTTP_PORT") ?? "8084";

// Register settings
builder.Services.AddSingleton(redisSettings);
builder.Services.AddSingleton(jwtSettings);
builder.Services.AddSingleton(persistenceSettings);
builder.Services.AddSingleton(corsSettings);

// JWT Authentication
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtSettings.Secret)),
            ValidateIssuer = false,
            ValidateAudience = false,
            ValidateLifetime = true,
            ClockSkew = TimeSpan.FromMinutes(1),
        };

        options.Events = new JwtBearerEvents
        {
            OnMessageReceived = context =>
            {
                // Support token from query string for SignalR WebSocket connections
                string? accessToken = context.Request.Query["access_token"];
                string? path = context.HttpContext.Request.Path.Value;
                if (!string.IsNullOrEmpty(accessToken) && path?.StartsWith("/hubs/", StringComparison.OrdinalIgnoreCase) == true)
                {
                    context.Token = accessToken;
                }

                return Task.CompletedTask;
            },
        };
    });
builder.Services.AddAuthorization();

// PostgreSQL with EF Core
string pgHost = Environment.GetEnvironmentVariable("POSTGRES_HOST") ?? "localhost";
string pgPort = Environment.GetEnvironmentVariable("POSTGRES_PORT") ?? "5432";
string pgUser = Environment.GetEnvironmentVariable("POSTGRES_USER") ?? "otterworks";
string pgPassword = Environment.GetEnvironmentVariable("POSTGRES_PASSWORD") ?? "otterworks";
string pgDb = Environment.GetEnvironmentVariable("POSTGRES_DB") ?? "otterworks";
string connectionString = $"Host={pgHost};Port={pgPort};Database={pgDb};Username={pgUser};Password={pgPassword}";

builder.Services.AddDbContext<CollabDbContext>(options =>
    options.UseNpgsql(connectionString));

// Services
builder.Services.AddSingleton<IRedisAdapter, OtterWorks.CollabService.Services.RedisAdapter>();
builder.Services.AddSingleton<IDocumentStore, DocumentStore>();
builder.Services.AddSingleton<IAwarenessService, AwarenessService>();

// SignalR
builder.Services.AddSignalR();

// CORS
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy.WithOrigins(corsSettings.GetOrigins())
              .AllowAnyHeader()
              .AllowAnyMethod()
              .AllowCredentials();
    });
});

// OpenTelemetry tracing
string otelEndpoint = Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT") ?? "http://localhost:4318";
string otelServiceName = Environment.GetEnvironmentVariable("OTEL_SERVICE_NAME") ?? "collab-service";

builder.Services.AddOpenTelemetry()
    .WithTracing(tracing =>
    {
        tracing
            .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService(otelServiceName))
            .AddAspNetCoreInstrumentation()
            .AddOtlpExporter(opts => opts.Endpoint = new Uri(otelEndpoint));
    });

// Prometheus metrics
builder.Services.AddSingleton(Metrics.DefaultRegistry);

// Health checks
builder.Services.AddHealthChecks();

// Memory cache
builder.Services.AddMemoryCache();

// Swagger
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

// Middleware pipeline
app.UseMiddleware<ErrorHandlingMiddleware>();
app.UseMiddleware<SecurityHeadersMiddleware>();
app.UseMiddleware<RequestLoggingMiddleware>();

// Prometheus metrics
app.UseHttpMetrics();

// CORS
app.UseCors();

// Authentication & Authorization
app.UseAuthentication();
app.UseAuthorization();

// Health check
app.MapGet("/health", () => Results.Ok(new
{
    status = "healthy",
    service = "collab-service",
    version = "0.1.0",
}));

// Prometheus metrics endpoint
app.MapGet("/metrics", async () =>
{
    using var stream = new MemoryStream();
    await Metrics.DefaultRegistry.CollectAndExportAsTextAsync(stream);
    stream.Position = 0;
    using var reader = new StreamReader(stream);
    string metricsText = await reader.ReadToEndAsync();
    return Results.Text(metricsText, "text/plain; version=0.0.4; charset=utf-8");
});

// Swagger
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

// Map REST API endpoints
app.MapCollabEndpoints();

// Map SignalR hub
app.MapHub<CollaborationHub>("/hubs/collaboration");

// Initialize Redis connection
try
{
    IRedisAdapter redis = app.Services.GetRequiredService<IRedisAdapter>();
    await redis.ConnectAsync();
    Log.Information("Redis connected");
}
catch (Exception ex)
{
    Log.Warning(ex, "Redis connection failed, starting without Redis persistence");
}

// Ensure database is created
using (IServiceScope scope = app.Services.CreateScope())
{
    try
    {
        CollabDbContext dbContext = scope.ServiceProvider.GetRequiredService<CollabDbContext>();
        await dbContext.Database.EnsureCreatedAsync();
        Log.Information("Database initialized");
    }
    catch (Exception ex)
    {
        Log.Warning(ex, "Database initialization failed, continuing without PostgreSQL");
    }
}

Log.Information("Collaboration service started on port {Port}", httpPort);

app.Run();

public partial class Program
{
}
