using Microsoft.AspNetCore.Mvc;
using OtterWorks.SearchService.Services;

namespace OtterWorks.SearchService.Controllers;

[ApiController]
public class HealthController : ControllerBase
{
    private readonly IMeiliSearchService _searchService;

    public HealthController(IMeiliSearchService searchService)
    {
        _searchService = searchService;
    }

    [HttpGet("/health")]
    public IActionResult Health()
    {
        return Ok(new { status = "healthy", service = "search-service", version = "0.1.0" });
    }

    [HttpGet("/health/ready")]
    public IActionResult Readiness()
    {
        bool healthy = _searchService.Ping();
        if (healthy)
            return Ok(new { ready = true });
        return StatusCode(503, new { ready = false, reason = "meilisearch_unavailable" });
    }
}
