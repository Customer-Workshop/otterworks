using Microsoft.AspNetCore.Mvc;

namespace OtterWorks.ReportService.Controllers;

[ApiController]
public class HealthController : ControllerBase
{
    [HttpGet("/health")]
    public IActionResult Health()
    {
        return Ok(new
        {
            status = "healthy",
            service = "report-service",
            version = "0.1.0",
        });
    }
}
