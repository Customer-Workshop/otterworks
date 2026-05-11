using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models;
using OtterWorks.AdminService.Models.Dto;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Controllers;

[ApiController]
[Route("api/v1/admin/users")]
public class UsersController : ControllerBase
{
    private readonly AdminDbContext _context;
    private readonly IAuditLogger _auditLogger;

    public UsersController(AdminDbContext context, IAuditLogger auditLogger)
    {
        _context = context;
        _auditLogger = auditLogger;
    }

    [HttpGet]
    public async Task<IActionResult> Index(
        [FromQuery] string? q,
        [FromQuery] string? role,
        [FromQuery] string? status,
        [FromQuery] int page = 1,
        [FromQuery] int per_page = 20)
    {
        page = Math.Max(page, 1);
        per_page = Math.Clamp(per_page, 1, 100);

        IQueryable<AdminUser> scope = _context.AdminUsers;

        if (!string.IsNullOrEmpty(q))
        {
            var escaped = EscapeLikePattern(q);
            scope = scope.Where(u => EF.Functions.ILike(u.Email, $"%{escaped}%") || EF.Functions.ILike(u.DisplayName, $"%{escaped}%"));
        }

        if (!string.IsNullOrEmpty(role))
        {
            scope = scope.Where(u => u.Role == role);
        }

        if (!string.IsNullOrEmpty(status))
        {
            scope = scope.Where(u => u.Status == status);
        }

        scope = scope.OrderByDescending(u => u.CreatedAt);

        var total = await scope.CountAsync();
        var records = await scope.Skip((page - 1) * per_page).Take(per_page).ToListAsync();

        Response.Headers["X-Total-Count"] = total.ToString(System.Globalization.CultureInfo.InvariantCulture);
        Response.Headers["X-Page"] = page.ToString(System.Globalization.CultureInfo.InvariantCulture);
        Response.Headers["X-Per-Page"] = per_page.ToString(System.Globalization.CultureInfo.InvariantCulture);

        return Ok(new AdminUsersListResponse
        {
            Users = records.Select(MapUser).ToList(),
            Total = total,
            Page = page,
            PerPage = per_page,
        });
    }

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> Show(Guid id)
    {
        var user = await _context.AdminUsers.Include(u => u.StorageQuota).FirstOrDefaultAsync(u => u.Id == id);
        if (user == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        var response = MapUser(user);
        if (user.StorageQuota != null)
        {
            response.StorageQuota = MapQuota(user.StorageQuota);
        }

        return Ok(response);
    }

    [HttpPut("{id:guid}")]
    public async Task<IActionResult> Update(Guid id, [FromBody] JsonElement body)
    {
        var user = await _context.AdminUsers.FindAsync(id);
        if (user == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        var userBody = body.TryGetProperty("user", out var userProp) ? userProp : body;
        var previousAttributes = new { user.Role, user.DisplayName, user.Email };

        if (userBody.TryGetProperty("email", out var emailProp))
        {
            user.Email = emailProp.GetString() ?? user.Email;
        }

        if (userBody.TryGetProperty("display_name", out var nameProp))
        {
            user.DisplayName = nameProp.GetString() ?? user.DisplayName;
        }

        if (userBody.TryGetProperty("role", out var roleProp))
        {
            var newRole = roleProp.GetString();
            if (newRole != null && !AdminUser.ValidRoles.Contains(newRole))
            {
                return UnprocessableEntity(new { error = "Validation failed", details = new[] { $"Role is not included in the list" } });
            }

            user.Role = newRole ?? user.Role;
        }

        if (userBody.TryGetProperty("avatar_url", out var avatarProp))
        {
            user.AvatarUrl = avatarProp.GetString();
        }

        user.UpdatedAt = DateTime.UtcNow;

        var validationErrors = ValidateUser(user);
        if (validationErrors.Count > 0)
        {
            return UnprocessableEntity(new { error = "Validation failed", details = validationErrors });
        }

        await _context.SaveChangesAsync();

        await _auditLogger.LogAsync(
            action: "user.updated",
            resourceType: "AdminUser",
            resourceId: user.Id,
            actorId: GetCurrentUserId(),
            actorEmail: GetCurrentUserEmail(),
            changesMade: new { before = previousAttributes, after = new { user.Role, user.DisplayName, user.Email } },
            ipAddress: HttpContext.Connection.RemoteIpAddress?.ToString(),
            userAgent: Request.Headers.UserAgent.FirstOrDefault());

        return Ok(MapUser(user));
    }

    [HttpDelete("{id:guid}")]
    public async Task<IActionResult> Destroy(Guid id)
    {
        var user = await _context.AdminUsers.FindAsync(id);
        if (user == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        user.SoftDelete();
        await _context.SaveChangesAsync();

        await _auditLogger.LogAsync(
            action: "user.deleted",
            resourceType: "AdminUser",
            resourceId: user.Id,
            actorId: GetCurrentUserId(),
            actorEmail: GetCurrentUserEmail(),
            ipAddress: HttpContext.Connection.RemoteIpAddress?.ToString(),
            userAgent: Request.Headers.UserAgent.FirstOrDefault());

        return NoContent();
    }

    [HttpPut("{id:guid}/suspend")]
    public async Task<IActionResult> Suspend(Guid id, [FromBody] JsonElement body)
    {
        var user = await _context.AdminUsers.FindAsync(id);
        if (user == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        string? reason = null;
        if (body.TryGetProperty("reason", out var reasonProp))
        {
            reason = reasonProp.GetString();
        }

        user.Suspend(reason);
        await _context.SaveChangesAsync();

        await _auditLogger.LogAsync(
            action: "user.suspended",
            resourceType: "AdminUser",
            resourceId: user.Id,
            actorId: GetCurrentUserId(),
            actorEmail: GetCurrentUserEmail(),
            changesMade: new { reason },
            ipAddress: HttpContext.Connection.RemoteIpAddress?.ToString(),
            userAgent: Request.Headers.UserAgent.FirstOrDefault());

        return Ok(MapUser(user));
    }

    [HttpPut("{id:guid}/activate")]
    public async Task<IActionResult> Activate(Guid id)
    {
        var user = await _context.AdminUsers.FindAsync(id);
        if (user == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        user.Activate();
        await _context.SaveChangesAsync();

        await _auditLogger.LogAsync(
            action: "user.activated",
            resourceType: "AdminUser",
            resourceId: user.Id,
            actorId: GetCurrentUserId(),
            actorEmail: GetCurrentUserEmail(),
            ipAddress: HttpContext.Connection.RemoteIpAddress?.ToString(),
            userAgent: Request.Headers.UserAgent.FirstOrDefault());

        return Ok(MapUser(user));
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

    private static string EscapeLikePattern(string input)
    {
        return input
            .Replace("\\", "\\\\", StringComparison.Ordinal)
            .Replace("%", "\\%", StringComparison.Ordinal)
            .Replace("_", "\\_", StringComparison.Ordinal);
    }

    private static List<string> ValidateUser(AdminUser user)
    {
        var errors = new List<string>();
        if (string.IsNullOrWhiteSpace(user.Email))
        {
            errors.Add("Email can't be blank");
        }

        if (string.IsNullOrWhiteSpace(user.DisplayName))
        {
            errors.Add("Display name can't be blank");
        }

        if (user.DisplayName?.Length > 255)
        {
            errors.Add("Display name is too long (maximum is 255 characters)");
        }

        if (!AdminUser.ValidRoles.Contains(user.Role))
        {
            errors.Add("Role is not included in the list");
        }

        if (!AdminUser.ValidStatuses.Contains(user.Status))
        {
            errors.Add("Status is not included in the list");
        }

        return errors;
    }

    private static AdminUserResponse MapUser(AdminUser user)
    {
        return new AdminUserResponse
        {
            Id = user.Id,
            Email = user.Email,
            DisplayName = user.DisplayName,
            Role = user.Role,
            Status = user.Status,
            AvatarUrl = user.AvatarUrl,
            Metadata = JsonSerializer.Deserialize<object>(user.Metadata),
            LastLoginAt = user.LastLoginAt,
            SuspendedAt = user.SuspendedAt,
            SuspendedReason = user.SuspendedReason,
            CreatedAt = user.CreatedAt,
            UpdatedAt = user.UpdatedAt,
        };
    }

    private static StorageQuotaResponse MapQuota(StorageQuota quota)
    {
        return new StorageQuotaResponse
        {
            Id = quota.Id,
            UserId = quota.UserId,
            QuotaBytes = quota.QuotaBytes,
            UsedBytes = quota.UsedBytes,
            Tier = quota.Tier,
            UsagePercentage = quota.UsagePercentage,
            OverQuota = quota.OverQuota,
            RemainingBytes = quota.RemainingBytes,
            CreatedAt = quota.CreatedAt,
            UpdatedAt = quota.UpdatedAt,
        };
    }
}
