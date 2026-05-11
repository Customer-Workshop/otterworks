using System.Text;
using FluentValidation;
using FluentValidation.AspNetCore;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OtterWorks.AuthService.Config;
using OtterWorks.AuthService.Data;
using OtterWorks.AuthService.Middleware;
using OtterWorks.AuthService.Services;
using Prometheus;
using Serilog;
using Serilog.Formatting.Compact;

var builder = WebApplication.CreateBuilder(args);

// Structured logging with Serilog
Log.Logger = new LoggerConfiguration()
    .ReadFrom.Configuration(builder.Configuration)
    .Enrich.WithProperty("service", "auth-service")
    .Enrich.FromLogContext()
    .WriteTo.Console(new CompactJsonFormatter())
    .CreateLogger();
builder.Host.UseSerilog();

// Configuration
var jwtSection = builder.Configuration.GetSection("Jwt");
var jwtEnvSecret = Environment.GetEnvironmentVariable("JWT_SECRET");
if (!string.IsNullOrEmpty(jwtEnvSecret))
{
    builder.Configuration["Jwt:Secret"] = jwtEnvSecret;
}

builder.Services.Configure<JwtSettings>(jwtSection);

// Override connection string from env vars used in docker-compose
var postgresHost = Environment.GetEnvironmentVariable("POSTGRES_HOST") ?? "localhost";
var postgresPort = Environment.GetEnvironmentVariable("POSTGRES_PORT") ?? "5432";
var postgresUser = Environment.GetEnvironmentVariable("POSTGRES_USER") ?? "otterworks";
var postgresPassword = Environment.GetEnvironmentVariable("POSTGRES_PASSWORD") ?? "otterworks_dev";
var postgresDb = Environment.GetEnvironmentVariable("POSTGRES_DB") ?? "otterworks";
var springUrl = Environment.GetEnvironmentVariable("SPRING_DATASOURCE_URL");
var springUser = Environment.GetEnvironmentVariable("SPRING_DATASOURCE_USERNAME");
var springPw = Environment.GetEnvironmentVariable("SPRING_DATASOURCE_PASSWORD");

string connectionString;
if (!string.IsNullOrEmpty(springUrl))
{
    var jdbcUri = new Uri(springUrl.Replace("jdbc:postgresql://", "http://", StringComparison.OrdinalIgnoreCase));
    connectionString = $"Host={jdbcUri.Host};Port={jdbcUri.Port};Database={jdbcUri.AbsolutePath.TrimStart('/')};Username={springUser ?? postgresUser};Password={springPw ?? postgresPassword}";
}
else
{
    connectionString = builder.Configuration.GetConnectionString("DefaultConnection")
        ?? $"Host={postgresHost};Port={postgresPort};Database={postgresDb};Username={postgresUser};Password={postgresPassword}";
}

// Entity Framework Core with PostgreSQL
builder.Services.AddDbContext<AuthDbContext>(options =>
    options.UseNpgsql(connectionString));

// JWT Authentication
var jwtSettings = jwtSection.Get<JwtSettings>() ?? new JwtSettings();
var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtSettings.Secret));

builder.Services.AddAuthentication(options =>
{
    options.DefaultAuthenticateScheme = JwtBearerDefaults.AuthenticationScheme;
    options.DefaultChallengeScheme = JwtBearerDefaults.AuthenticationScheme;
})
.AddJwtBearer(options =>
{
    options.TokenValidationParameters = new TokenValidationParameters
    {
        ValidateIssuerSigningKey = true,
        IssuerSigningKey = key,
        ValidateIssuer = false,
        ValidateAudience = false,
        ValidateLifetime = true,
        ClockSkew = TimeSpan.Zero,
        RoleClaimType = "roles",
    };
});

builder.Services.AddAuthorization();

// Services
builder.Services.AddSingleton<IJwtTokenProvider, JwtTokenProvider>();
builder.Services.AddScoped<IAuthService, OtterWorks.AuthService.Services.AuthService>();
builder.Services.AddScoped<IUserService, UserService>();
builder.Services.AddScoped<IUserSettingsService, UserSettingsService>();

// FluentValidation
builder.Services.AddFluentValidationAutoValidation();
builder.Services.AddValidatorsFromAssemblyContaining<Program>();

// Controllers
builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.PropertyNamingPolicy = System.Text.Json.JsonNamingPolicy.CamelCase;
    });

// Swagger
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// OpenTelemetry tracing
var otelEndpoint = Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT");
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing =>
    {
        tracing
            .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("auth-service"))
            .AddAspNetCoreInstrumentation();
        if (!string.IsNullOrEmpty(otelEndpoint))
        {
            tracing.AddOtlpExporter();
        }
    });

// Prometheus metrics
builder.Services.AddSingleton(Metrics.DefaultRegistry);

var app = builder.Build();

// Middleware pipeline
app.UseMiddleware<SecurityHeadersMiddleware>();
app.UseMiddleware<ErrorHandlingMiddleware>();
app.UseMiddleware<RequestLoggingMiddleware>();

app.UseHttpMetrics();
app.UseAuthentication();
app.UseAuthorization();

app.MapControllers();

// Prometheus metrics endpoint
app.MapGet("/metrics", async () =>
{
    using var stream = new MemoryStream();
    await Metrics.DefaultRegistry.CollectAndExportAsTextAsync(stream);
    stream.Position = 0;
    using var reader = new StreamReader(stream);
    var metricsText = await reader.ReadToEndAsync();
    return Results.Text(metricsText, "text/plain; version=0.0.4; charset=utf-8");
}).AllowAnonymous();

app.Run();

public partial class Program
{
}
