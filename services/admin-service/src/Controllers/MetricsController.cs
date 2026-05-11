using Microsoft.AspNetCore.Mvc;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Controllers;

[ApiController]
[Route("api/v1/admin/metrics")]
public class MetricsController : ControllerBase
{
    private readonly IMetricsAggregator _metricsAggregator;

    public MetricsController(IMetricsAggregator metricsAggregator)
    {
        _metricsAggregator = metricsAggregator;
    }

    [HttpGet("summary")]
    public async Task<IActionResult> Summary()
    {
        var result = await _metricsAggregator.GetSummaryAsync();
        return Ok(result);
    }
}
