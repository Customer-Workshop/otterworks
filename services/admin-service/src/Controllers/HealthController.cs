using Microsoft.AspNetCore.Mvc;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models.Dto;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Controllers;

[ApiController]
public class HealthController : ControllerBase
{
    private readonly IHealthChecker _healthChecker;
    private readonly AdminDbContext _context;

    public HealthController(IHealthChecker healthChecker, AdminDbContext context)
    {
        _healthChecker = healthChecker;
        _context = context;
    }

    [HttpGet("/health")]
    public async Task<IActionResult> GetHealth()
    {
        try
        {
            var canConnect = await _context.Database.CanConnectAsync();
            if (!canConnect)
            {
                return StatusCode(503, new HealthResponse { Status = "degraded" });
            }
        }
        catch
        {
            return StatusCode(503, new HealthResponse { Status = "degraded" });
        }

        return Ok(new HealthResponse());
    }

    [HttpGet("/api/v1/admin/health/services")]
    public async Task<IActionResult> GetServices()
    {
        var result = await _healthChecker.CheckAllAsync();
        var statusCode = result.Status == "healthy" ? 200 : 503;
        return StatusCode(statusCode, result);
    }
}
