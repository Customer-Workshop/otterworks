using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models;
using OtterWorks.AdminService.Models.Dto;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Controllers;

[ApiController]
[Route("api/v1/admin/announcements")]
public class AnnouncementsController : ControllerBase
{
    private readonly AdminDbContext _context;
    private readonly IAuditLogger _auditLogger;

    public AnnouncementsController(AdminDbContext context, IAuditLogger auditLogger)
    {
        _context = context;
        _auditLogger = auditLogger;
    }

    [HttpGet]
    public async Task<IActionResult> Index(
        [FromQuery] string? status,
        [FromQuery] string? severity,
        [FromQuery] string? active,
        [FromQuery] int page = 1,
        [FromQuery] int per_page = 20)
    {
        page = Math.Max(page, 1);
        per_page = Math.Clamp(per_page, 1, 100);

        IQueryable<Announcement> scope = _context.Announcements;

        if (!string.IsNullOrEmpty(status))
        {
            scope = scope.Where(a => a.Status == status);
        }

        if (!string.IsNullOrEmpty(severity))
        {
            scope = scope.Where(a => a.Severity == severity);
        }

        if (active == "true")
        {
            var now = DateTime.UtcNow;
            scope = scope.Where(a =>
                a.Status == "published" &&
                (!a.StartsAt.HasValue || a.StartsAt <= now) &&
                (!a.EndsAt.HasValue || a.EndsAt >= now));
        }

        scope = scope.OrderByDescending(a => a.CreatedAt);

        var total = await scope.CountAsync();
        var records = await scope.Skip((page - 1) * per_page).Take(per_page).ToListAsync();

        return Ok(new AnnouncementsListResponse
        {
            Announcements = records.Select(MapAnnouncement).ToList(),
            Total = total,
            Page = page,
            PerPage = per_page,
        });
    }

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> Show(Guid id)
    {
        var announcement = await _context.Announcements.FindAsync(id);
        if (announcement == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        return Ok(MapAnnouncement(announcement));
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] JsonElement body)
    {
        var annBody = body.TryGetProperty("announcement", out var annProp) ? annProp : body;

        var announcement = new Announcement
        {
            Id = Guid.NewGuid(),
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
            CreatedBy = GetCurrentUserId(),
        };

        if (annBody.TryGetProperty("title", out var titleProp))
        {
            announcement.Title = titleProp.GetString() ?? string.Empty;
        }

        if (annBody.TryGetProperty("body", out var bodyProp))
        {
            announcement.Body = bodyProp.GetString() ?? string.Empty;
        }

        if (annBody.TryGetProperty("severity", out var sevProp))
        {
            announcement.Severity = sevProp.GetString() ?? "info";
        }

        if (annBody.TryGetProperty("status", out var statusProp))
        {
            announcement.Status = statusProp.GetString() ?? "draft";
        }

        if (annBody.TryGetProperty("starts_at", out var startsProp) && startsProp.ValueKind != JsonValueKind.Null)
        {
            announcement.StartsAt = startsProp.GetDateTime();
        }

        if (annBody.TryGetProperty("ends_at", out var endsProp) && endsProp.ValueKind != JsonValueKind.Null)
        {
            announcement.EndsAt = endsProp.GetDateTime();
        }

        if (annBody.TryGetProperty("target_audience", out var audienceProp))
        {
            announcement.TargetAudience = audienceProp.GetRawText();
        }

        var validationErrors = ValidateAnnouncement(announcement);
        if (validationErrors.Count > 0)
        {
            return UnprocessableEntity(new { error = "Validation failed", details = validationErrors });
        }

        _context.Announcements.Add(announcement);
        await _context.SaveChangesAsync();

        await _auditLogger.LogAsync(
            action: "announcement.created",
            resourceType: "Announcement",
            resourceId: announcement.Id,
            actorId: GetCurrentUserId(),
            actorEmail: GetCurrentUserEmail(),
            ipAddress: HttpContext.Connection.RemoteIpAddress?.ToString(),
            userAgent: Request.Headers.UserAgent.FirstOrDefault());

        return StatusCode(201, MapAnnouncement(announcement));
    }

    [HttpPut("{id:guid}")]
    public async Task<IActionResult> Update(Guid id, [FromBody] JsonElement body)
    {
        var announcement = await _context.Announcements.FindAsync(id);
        if (announcement == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        var annBody = body.TryGetProperty("announcement", out var annProp) ? annProp : body;

        if (annBody.TryGetProperty("title", out var titleProp))
        {
            announcement.Title = titleProp.GetString() ?? announcement.Title;
        }

        if (annBody.TryGetProperty("body", out var bodyProp))
        {
            announcement.Body = bodyProp.GetString() ?? announcement.Body;
        }

        if (annBody.TryGetProperty("severity", out var sevProp))
        {
            announcement.Severity = sevProp.GetString() ?? announcement.Severity;
        }

        if (annBody.TryGetProperty("status", out var statusProp))
        {
            announcement.Status = statusProp.GetString() ?? announcement.Status;
        }

        if (annBody.TryGetProperty("starts_at", out var startsProp))
        {
            announcement.StartsAt = startsProp.ValueKind == JsonValueKind.Null ? null : startsProp.GetDateTime();
        }

        if (annBody.TryGetProperty("ends_at", out var endsProp))
        {
            announcement.EndsAt = endsProp.ValueKind == JsonValueKind.Null ? null : endsProp.GetDateTime();
        }

        if (annBody.TryGetProperty("target_audience", out var audienceProp))
        {
            announcement.TargetAudience = audienceProp.GetRawText();
        }

        announcement.UpdatedAt = DateTime.UtcNow;

        var validationErrors = ValidateAnnouncement(announcement);
        if (validationErrors.Count > 0)
        {
            return UnprocessableEntity(new { error = "Validation failed", details = validationErrors });
        }

        await _context.SaveChangesAsync();

        await _auditLogger.LogAsync(
            action: "announcement.updated",
            resourceType: "Announcement",
            resourceId: announcement.Id,
            actorId: GetCurrentUserId(),
            actorEmail: GetCurrentUserEmail(),
            ipAddress: HttpContext.Connection.RemoteIpAddress?.ToString(),
            userAgent: Request.Headers.UserAgent.FirstOrDefault());

        return Ok(MapAnnouncement(announcement));
    }

    [HttpDelete("{id:guid}")]
    public async Task<IActionResult> Destroy(Guid id)
    {
        var announcement = await _context.Announcements.FindAsync(id);
        if (announcement == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        _context.Announcements.Remove(announcement);
        await _context.SaveChangesAsync();

        await _auditLogger.LogAsync(
            action: "announcement.deleted",
            resourceType: "Announcement",
            resourceId: announcement.Id,
            actorId: GetCurrentUserId(),
            actorEmail: GetCurrentUserEmail(),
            ipAddress: HttpContext.Connection.RemoteIpAddress?.ToString(),
            userAgent: Request.Headers.UserAgent.FirstOrDefault());

        return NoContent();
    }

    private Guid? GetCurrentUserId()
    {
        var value = HttpContext.Items["jwt.user_id"] as string;
        return Guid.TryParse(value, out var id) ? id : null;
    }

    private string? GetCurrentUserEmail()
    {
        return HttpContext.Items["jwt.user_email"] as string;
    }

    private static List<string> ValidateAnnouncement(Announcement ann)
    {
        var errors = new List<string>();
        if (string.IsNullOrWhiteSpace(ann.Title))
        {
            errors.Add("Title can't be blank");
        }

        if (ann.Title?.Length > 255)
        {
            errors.Add("Title is too long (maximum is 255 characters)");
        }

        if (string.IsNullOrWhiteSpace(ann.Body))
        {
            errors.Add("Body can't be blank");
        }

        if (!Announcement.ValidSeverities.Contains(ann.Severity))
        {
            errors.Add("Severity is not included in the list");
        }

        if (!Announcement.ValidStatuses.Contains(ann.Status))
        {
            errors.Add("Status is not included in the list");
        }

        if (ann.StartsAt.HasValue && ann.EndsAt.HasValue && ann.EndsAt <= ann.StartsAt)
        {
            errors.Add("Ends at must be after starts_at");
        }

        return errors;
    }

    private static AnnouncementResponse MapAnnouncement(Announcement ann)
    {
        return new AnnouncementResponse
        {
            Id = ann.Id,
            Title = ann.Title,
            Body = ann.Body,
            Severity = ann.Severity,
            Status = ann.Status,
            TargetAudience = JsonSerializer.Deserialize<object>(ann.TargetAudience),
            StartsAt = ann.StartsAt,
            EndsAt = ann.EndsAt,
            CreatedBy = ann.CreatedBy,
            Active = ann.Active,
            CreatedAt = ann.CreatedAt,
            UpdatedAt = ann.UpdatedAt,
        };
    }
}
