using FluentValidation;
using Microsoft.AspNetCore.Mvc;
using OtterWorks.ReportService.Models;
using OtterWorks.ReportService.Services;

namespace OtterWorks.ReportService.Controllers;

[ApiController]
[Route("api/v1/reports")]
public class ReportController : ControllerBase
{
    private readonly IReportService _reportService;
    private readonly IValidator<ReportRequest> _validator;
    private readonly ILogger<ReportController> _logger;

    public ReportController(
        IReportService reportService,
        IValidator<ReportRequest> validator,
        ILogger<ReportController> logger)
    {
        _reportService = reportService;
        _validator = validator;
        _logger = logger;
    }

    [HttpPost]
    [ProducesResponseType(typeof(ReportResponse), StatusCodes.Status202Accepted)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<IActionResult> CreateReport([FromBody] ReportRequest request)
    {
        var validation = await _validator.ValidateAsync(request);
        if (!validation.IsValid)
        {
            return BadRequest(new { errors = validation.Errors.Select(e => e.ErrorMessage) });
        }

        _logger.LogInformation("Report request: name={Name}, category={Category}, type={Type}, by={By}",
            request.ReportName, request.Category, request.ReportType, request.RequestedBy);

        var report = await _reportService.CreateReportAsync(request);
        return StatusCode(StatusCodes.Status202Accepted, ReportResponse.FromEntity(report));
    }

    [HttpGet("{id:long}")]
    [ProducesResponseType(typeof(ReportResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> GetReport(long id)
    {
        var report = await _reportService.GetReportAsync(id);
        if (report == null)
        {
            return NotFound();
        }
        return Ok(ReportResponse.FromEntity(report));
    }

    [HttpGet]
    [ProducesResponseType(StatusCodes.Status200OK)]
    public async Task<IActionResult> ListReports(
        [FromQuery] string? userId = null,
        [FromQuery] ReportStatus? status = null)
    {
        List<Report> reports;
        if (userId != null)
        {
            reports = await _reportService.GetReportsByUserAsync(userId);
        }
        else if (status != null)
        {
            reports = await _reportService.GetReportsByStatusAsync(status.Value);
        }
        else
        {
            reports = await _reportService.GetReportsByStatusAsync(ReportStatus.COMPLETED);
        }

        var responses = reports.Select(ReportResponse.FromEntity).ToList();
        return Ok(new { reports = responses, total = responses.Count });
    }

    [HttpGet("{id:long}/download")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<IActionResult> DownloadReport(long id)
    {
        var report = await _reportService.GetReportAsync(id);
        if (report == null)
        {
            return NotFound();
        }

        if (report.Status == ReportStatus.GENERATING || report.Status == ReportStatus.PENDING)
        {
            return Conflict();
        }

        if (report.Status == ReportStatus.FAILED || report.FilePath == null)
        {
            return NotFound();
        }

        if (!System.IO.File.Exists(report.FilePath))
        {
            _logger.LogWarning("Report file missing: {Path}", report.FilePath);
            return NotFound();
        }

        var fileContent = await System.IO.File.ReadAllBytesAsync(report.FilePath);
        var contentType = GetContentType(report.ReportType);
        var fileName = Path.GetFileName(report.FilePath);

        return File(fileContent, contentType, fileName);
    }

    [HttpDelete("{id:long}")]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> DeleteReport(long id)
    {
        var deleted = await _reportService.DeleteReportAsync(id);
        if (!deleted)
        {
            return NotFound();
        }
        return NoContent();
    }

    private static string GetContentType(ReportType reportType) => reportType switch
    {
        ReportType.PDF => "application/pdf",
        ReportType.CSV => "text/csv",
        ReportType.EXCEL => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        _ => "application/octet-stream"
    };
}
