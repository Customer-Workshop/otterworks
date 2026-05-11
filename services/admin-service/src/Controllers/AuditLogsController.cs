using System.Globalization;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models;
using OtterWorks.AdminService.Models.Dto;

namespace OtterWorks.AdminService.Controllers;

[ApiController]
[Route("api/v1/admin/audit-logs")]
public class AuditLogsController : ControllerBase
{
    private readonly AdminDbContext _context;

    public AuditLogsController(AdminDbContext context)
    {
        _context = context;
    }

    [HttpGet]
    public async Task<IActionResult> Index(
        [FromQuery] string? action_type,
        [FromQuery] string? resource_type,
        [FromQuery] string? resource_id,
        [FromQuery] string? actor_id,
        [FromQuery] string? since,
        [FromQuery] string? until,
        [FromQuery] int page = 1,
        [FromQuery] int per_page = 20)
    {
        page = Math.Max(page, 1);
        per_page = Math.Clamp(per_page, 1, 100);

        IQueryable<AuditLog> scope = _context.AuditLogs.OrderByDescending(l => l.CreatedAt);

        if (!string.IsNullOrEmpty(action_type))
        {
            scope = scope.Where(l => l.Action == action_type);
        }

        if (!string.IsNullOrEmpty(resource_type))
        {
            scope = scope.Where(l => l.ResourceType == resource_type);
            if (!string.IsNullOrEmpty(resource_id) && Guid.TryParse(resource_id, out var resId))
            {
                scope = scope.Where(l => l.ResourceId == resId);
            }
        }

        if (!string.IsNullOrEmpty(actor_id) && Guid.TryParse(actor_id, out var actId))
        {
            scope = scope.Where(l => l.ActorId == actId);
        }

        if (!string.IsNullOrEmpty(since))
        {
            if (!DateTime.TryParse(since, CultureInfo.InvariantCulture, DateTimeStyles.None, out var sinceDate))
            {
                return BadRequest(new { error = $"Invalid date format: {since}" });
            }

            scope = scope.Where(l => l.CreatedAt >= sinceDate);
        }

        if (!string.IsNullOrEmpty(until))
        {
            if (!DateTime.TryParse(until, CultureInfo.InvariantCulture, DateTimeStyles.None, out var untilDate))
            {
                return BadRequest(new { error = $"Invalid date format: {until}" });
            }

            scope = scope.Where(l => l.CreatedAt <= untilDate);
        }

        var total = await scope.CountAsync();
        var records = await scope.Skip((page - 1) * per_page).Take(per_page).ToListAsync();

        return Ok(new AuditLogsListResponse
        {
            AuditLogs = records.Select(MapAuditLog).ToList(),
            Total = total,
            Page = page,
            PerPage = per_page,
        });
    }

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> Show(Guid id)
    {
        var log = await _context.AuditLogs.FindAsync(id);
        if (log == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        return Ok(MapAuditLog(log));
    }

    private static AuditLogResponse MapAuditLog(AuditLog log)
    {
        return new AuditLogResponse
        {
            Id = log.Id,
            ActorId = log.ActorId,
            ActorEmail = log.ActorEmail,
            Action = log.Action,
            ResourceType = log.ResourceType,
            ResourceId = log.ResourceId,
            ChangesMade = JsonSerializer.Deserialize<object>(log.ChangesMade),
            IpAddress = log.IpAddress,
            UserAgent = log.UserAgent,
            CreatedAt = log.CreatedAt,
        };
    }
}
