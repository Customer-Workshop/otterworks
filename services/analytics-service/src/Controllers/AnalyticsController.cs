using System.Text;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using OtterWorks.AnalyticsService.Models;
using OtterWorks.AnalyticsService.Services;

namespace OtterWorks.AnalyticsService.Controllers;

[ApiController]
[Route("api/v1/analytics")]
[Authorize]
public class AnalyticsController : ControllerBase
{
    private readonly IAnalyticsService _analyticsService;
    private readonly ILogger<AnalyticsController> _logger;

    public AnalyticsController(IAnalyticsService analyticsService, ILogger<AnalyticsController> logger)
    {
        _analyticsService = analyticsService;
        _logger = logger;
    }

    [HttpPost("events")]
    [AllowAnonymous]
    public async Task<IActionResult> TrackEvent([FromBody] TrackEventRequest request)
    {
        var analyticsEvent = await _analyticsService.TrackEventAsync(
            request.EventType,
            request.UserId,
            request.ResourceId,
            request.ResourceType,
            request.Metadata ?? new Dictionary<string, string>());

        _logger.LogInformation("Event tracked: {EventId}", analyticsEvent.EventId);

        return Accepted(new AcceptedResponse
        {
            Status = "accepted",
            EventId = analyticsEvent.EventId,
        });
    }

    [HttpGet("dashboard")]
    [AllowAnonymous]
    public async Task<IActionResult> GetDashboard([FromQuery] string period = "7d")
    {
        var summary = await _analyticsService.GetDashboardSummaryAsync(period);
        return Ok(summary);
    }

    [HttpGet("users/{userId}/activity")]
    [AllowAnonymous]
    public async Task<IActionResult> GetUserActivity(string userId)
    {
        var activity = await _analyticsService.GetUserActivityAsync(userId);
        return Ok(activity);
    }

    [HttpGet("documents/{documentId}/stats")]
    [AllowAnonymous]
    public async Task<IActionResult> GetDocumentStats(string documentId)
    {
        var stats = await _analyticsService.GetDocumentStatsAsync(documentId);
        return Ok(stats);
    }

    [HttpGet("top-content")]
    [AllowAnonymous]
    public async Task<IActionResult> GetTopContent(
        [FromQuery] string type = "documents",
        [FromQuery] string period = "7d",
        [FromQuery] int limit = 10)
    {
        var response = await _analyticsService.GetTopContentAsync(type, period, limit);
        return Ok(response);
    }

    [HttpGet("active-users")]
    [AllowAnonymous]
    public async Task<IActionResult> GetActiveUsers([FromQuery] string period = "daily")
    {
        var response = await _analyticsService.GetActiveUsersAsync(period);
        return Ok(response);
    }

    [HttpGet("storage")]
    [AllowAnonymous]
    public async Task<IActionResult> GetStorageUsage([FromQuery(Name = "user_id")] string? userId = null)
    {
        var response = await _analyticsService.GetStorageUsageAsync(userId);
        return Ok(response);
    }

    [HttpGet("export")]
    [AllowAnonymous]
    public async Task<IActionResult> ExportReport(
        [FromQuery] string format = "json",
        [FromQuery] string period = "7d")
    {
        if (format == "csv")
        {
            var report = await _analyticsService.ExportReportAsync("csv", period);
            var csvContent = BuildCsvContent(report.Data);
            return Content(csvContent, "text/plain; charset=utf-8");
        }

        var jsonReport = await _analyticsService.ExportReportAsync("json", period);
        return Ok(jsonReport);
    }

    private static string BuildCsvContent(List<Dictionary<string, string>> data)
    {
        var headers = new[] { "event_id", "event_type", "user_id", "resource_id", "resource_type", "timestamp" };
        var sb = new StringBuilder();
        sb.AppendLine(string.Join(",", headers));

        foreach (var row in data)
        {
            var values = headers.Select(h => EscapeCsvField(row.TryGetValue(h, out var v) ? v : string.Empty));
            sb.AppendLine(string.Join(",", values));
        }

        return sb.ToString();
    }

    private static string EscapeCsvField(string value)
    {
        if (value.Contains(',') || value.Contains('"') || value.Contains('\n'))
        {
            return "\"" + value.Replace("\"", "\"\"") + "\"";
        }

        return value;
    }
}
