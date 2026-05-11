using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using OtterWorks.AuthService.Data;

namespace OtterWorks.AuthService.Controllers;

[ApiController]
public class HealthController : ControllerBase
{
    private readonly AuthDbContext _db;
    private readonly ILogger<HealthController> _logger;

    public HealthController(AuthDbContext db, ILogger<HealthController> logger)
    {
        _db = db;
        _logger = logger;
    }

    [HttpGet("health")]
    [AllowAnonymous]
    public IActionResult Health()
    {
        var dbHealthy = CheckDatabaseConnectivity();

        var response = new
        {
            status = dbHealthy ? "healthy" : "degraded",
            service = "auth-service",
            version = "0.1.0",
            database = new { status = dbHealthy ? "up" : "down" },
        };

        return dbHealthy ? Ok(response) : StatusCode(StatusCodes.Status503ServiceUnavailable, response);
    }

    private bool CheckDatabaseConnectivity()
    {
        try
        {
            return _db.Database.CanConnect();
        }
        catch (Exception ex)
        {
            _logger.LogWarning("Database health check failed: {Message}", ex.Message);
            return false;
        }
    }
}
