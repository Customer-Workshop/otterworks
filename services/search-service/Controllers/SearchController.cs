using System.Globalization;
using Microsoft.AspNetCore.Mvc;
using OtterWorks.SearchService.Models;
using OtterWorks.SearchService.Services;
namespace OtterWorks.SearchService.Controllers;

[ApiController]
[Route("api/v1/search")]
public class SearchController : ControllerBase
{
    private readonly IMeiliSearchService _searchService;
    private readonly ISearchAnalyticsTracker _analytics;
    private readonly Serilog.ILogger _logger = Serilog.Log.ForContext<SearchController>();

    public SearchController(IMeiliSearchService searchService, ISearchAnalyticsTracker analytics)
    {
        _searchService = searchService;
        _analytics = analytics;
    }

    [HttpGet("")]
    public IActionResult SearchDocuments(
        [FromQuery] string? q,
        [FromQuery] string? type,
        [FromQuery] string? page,
        [FromQuery] string? size)
    {
        int pageNum;
        int pageSize;
        try
        {
            pageNum = Math.Max(1, int.Parse(page ?? "1", CultureInfo.InvariantCulture));
            pageSize = Math.Max(1, Math.Min(100, int.Parse(size ?? "20", CultureInfo.InvariantCulture)));
        }
        catch (Exception ex) when (ex is FormatException or OverflowException)
        {
            return BadRequest(new { error = "Invalid page or size parameter" });
        }

        string? ownerId = Request.Headers.TryGetValue("X-User-ID", out var userIdHeader)
            ? userIdHeader.ToString().Trim()
            : null;
        if (string.IsNullOrEmpty(ownerId)) ownerId = null;

        if (string.IsNullOrEmpty(q))
            return BadRequest(new { error = "Query parameter 'q' is required" });

        try
        {
            var results = _searchService.Search(
                query: q,
                docType: type,
                ownerId: ownerId,
                page: pageNum,
                pageSize: pageSize);

            _logger.Information("Search executed: {Query}, results: {Count}", q, results.Total);
            return Ok(results.ToDict());
        }
        catch (ArgumentException e)
        {
            return BadRequest(new { error = e.Message });
        }
        catch (Exception ex)
        {
            _logger.Error(ex, "Search failed: {Query}", q);
            return StatusCode(500, new { error = "Search failed" });
        }
    }

    [HttpGet("suggest")]
    public IActionResult Suggest([FromQuery] string? q)
    {
        string prefix = q ?? string.Empty;
        if (string.IsNullOrEmpty(prefix) || prefix.Length < 2)
            return Ok(new { suggestions = Array.Empty<string>(), query = prefix });

        try
        {
            var suggestions = _searchService.Suggest(prefix);
            return Ok(new { suggestions, query = prefix });
        }
        catch (Exception ex)
        {
            _logger.Error(ex, "Suggest failed: {Prefix}", prefix);
            return Ok(new { suggestions = Array.Empty<string>(), query = prefix });
        }
    }

    [HttpPost("advanced")]
    public IActionResult AdvancedSearch([FromBody] AdvancedSearchRequest? request)
    {
        request ??= new AdvancedSearchRequest();

        int pageNum;
        int pageSize;
        try
        {
            pageNum = Math.Max(request.Page ?? 1, 1);
            pageSize = Math.Min(Math.Max(request.Size ?? 20, 1), 100);
        }
        catch (Exception ex) when (ex is FormatException or OverflowException)
        {
            return BadRequest(new { error = "Invalid page or size parameter" });
        }

        string? ownerId = Request.Headers.TryGetValue("X-User-ID", out var userIdHeader)
            ? userIdHeader.ToString().Trim()
            : null;
        if (string.IsNullOrEmpty(ownerId)) ownerId = null;

        try
        {
            var results = _searchService.AdvancedSearch(
                query: request.Q,
                docType: request.Type,
                ownerId: ownerId,
                tags: request.Tags,
                dateFrom: request.DateFrom,
                dateTo: request.DateTo,
                page: pageNum,
                pageSize: pageSize);

            _logger.Information("Advanced search executed: {Query}, results: {Count}", request.Q, results.Total);
            return Ok(results.ToDict());
        }
        catch (Exception ex)
        {
            _logger.Error(ex, "Advanced search failed");
            return StatusCode(500, new { error = "Advanced search failed" });
        }
    }

    [HttpGet("analytics")]
    public IActionResult Analytics()
    {
        try
        {
            var data = _analytics.GetAnalytics();
            return Ok(data.ToDict());
        }
        catch (Exception ex)
        {
            _logger.Error(ex, "Analytics failed");
            return StatusCode(500, new { error = "Failed to retrieve analytics" });
        }
    }
}
