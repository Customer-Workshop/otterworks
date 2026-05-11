using System.Diagnostics;
using Microsoft.EntityFrameworkCore;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models.Dto;

namespace OtterWorks.AdminService.Services;

public interface IHealthChecker
{
    Task<ServiceHealthResponse> CheckAllAsync();
}

public class HealthChecker : IHealthChecker
{
    private static readonly string[] ServiceNames =
    [
        "auth-service", "file-service", "document-service", "collab-service",
        "notification-service", "search-service", "analytics-service", "audit-service"
    ];

    private readonly AdminDbContext _context;
    private readonly IConfiguration _configuration;
    private readonly IHttpClientFactory _httpClientFactory;

    public HealthChecker(AdminDbContext context, IConfiguration configuration, IHttpClientFactory httpClientFactory)
    {
        _context = context;
        _configuration = configuration;
        _httpClientFactory = httpClientFactory;
    }

    public async Task<ServiceHealthResponse> CheckAllAsync()
    {
        var services = new List<ServiceStatus>();
        foreach (var name in ServiceNames)
        {
            services.Add(await CheckServiceAsync(name));
        }

        var overall = services.All(s => s.Status == "healthy") ? "healthy" : "degraded";

        return new ServiceHealthResponse
        {
            Status = overall,
            Timestamp = DateTime.UtcNow.ToString("o"),
            Services = services,
            Database = await CheckDatabaseAsync(),
            Redis = CheckRedis(),
        };
    }

    private async Task<ServiceStatus> CheckServiceAsync(string name)
    {
        var envKey = name.Replace("-", "_", StringComparison.Ordinal).ToUpperInvariant();
        var host = _configuration[$"{envKey}_HOST"] ?? name;
        var port = _configuration[$"{envKey}_PORT"];

        if (string.IsNullOrEmpty(port))
        {
            return new ServiceStatus { Name = name, Status = "unknown", LatencyMs = 0, Message = "No endpoint configured" };
        }

        var sw = Stopwatch.StartNew();
        try
        {
            var client = _httpClientFactory.CreateClient();
            client.Timeout = TimeSpan.FromSeconds(2);
            var response = await client.GetAsync(new Uri($"http://{host}:{port}/health"));
            sw.Stop();
            return new ServiceStatus
            {
                Name = name,
                Status = response.IsSuccessStatusCode ? "healthy" : "unhealthy",
                LatencyMs = Math.Round(sw.Elapsed.TotalMilliseconds, 1),
            };
        }
        catch (Exception ex)
        {
            sw.Stop();
            return new ServiceStatus
            {
                Name = name,
                Status = "unhealthy",
                LatencyMs = Math.Round(sw.Elapsed.TotalMilliseconds, 1),
                Message = ex.Message,
            };
        }
    }

    private async Task<ComponentHealth> CheckDatabaseAsync()
    {
        var sw = Stopwatch.StartNew();
        try
        {
            await _context.Database.ExecuteSqlRawAsync("SELECT 1");
            sw.Stop();
            return new ComponentHealth { Status = "healthy", LatencyMs = Math.Round(sw.Elapsed.TotalMilliseconds, 1) };
        }
        catch (Exception ex)
        {
            sw.Stop();
            return new ComponentHealth { Status = "unhealthy", Message = ex.Message };
        }
    }

    private ComponentHealth CheckRedis()
    {
        var redisHost = _configuration["REDIS_HOST"] ?? "localhost";
        var redisPort = _configuration["REDIS_PORT"] ?? "6379";

        try
        {
            using var client = new System.Net.Sockets.TcpClient();
            var sw = Stopwatch.StartNew();
            client.Connect(redisHost, int.Parse(redisPort, System.Globalization.CultureInfo.InvariantCulture));
            sw.Stop();
            return new ComponentHealth { Status = "healthy", LatencyMs = Math.Round(sw.Elapsed.TotalMilliseconds, 1) };
        }
        catch (Exception ex)
        {
            return new ComponentHealth { Status = "unhealthy", Message = ex.Message };
        }
    }
}
