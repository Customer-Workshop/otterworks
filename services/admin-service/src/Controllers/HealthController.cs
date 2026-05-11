using Microsoft.AspNetCore.Mvc;
using OtterWorks.AdminService.Models.Dto;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Controllers;

[ApiController]
public class HealthController : ControllerBase
{
    private readonly IHealthChecker _healthChecker;

    public HealthController(IHealthChecker healthChecker)
    {
        _healthChecker = healthChecker;
    }

    [HttpGet("/health")]
    public IActionResult GetHealth()
    {
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
