using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models;
using OtterWorks.AdminService.Models.Dto;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Controllers;

[ApiController]
[Route("api/v1/admin/features")]
public class FeaturesController : ControllerBase
{
    private readonly AdminDbContext _context;
    private readonly IAuditLogger _auditLogger;

    public FeaturesController(AdminDbContext context, IAuditLogger auditLogger)
    {
        _context = context;
        _auditLogger = auditLogger;
    }

    [HttpGet]
    public async Task<IActionResult> Index(
        [FromQuery] string? enabled,
        [FromQuery] int page = 1,
        [FromQuery] int per_page = 20)
    {
        page = Math.Max(page, 1);
        per_page = Math.Clamp(per_page, 1, 100);

        IQueryable<FeatureFlag> scope = _context.FeatureFlags;

        if (enabled == "true")
        {
            scope = scope.Where(f => f.Enabled);
        }
        else if (enabled == "false")
        {
            scope = scope.Where(f => !f.Enabled);
        }

        scope = scope.OrderBy(f => f.Name);

        var total = await scope.CountAsync();
        var records = await scope.Skip((page - 1) * per_page).Take(per_page).ToListAsync();

        return Ok(new FeatureFlagsListResponse
        {
            Features = records.Select(MapFeatureFlag).ToList(),
            Total = total,
            Page = page,
            PerPage = per_page,
        });
    }

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> Show(Guid id)
    {
        var flag = await _context.FeatureFlags.FindAsync(id);
        if (flag == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        return Ok(MapFeatureFlag(flag));
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] JsonElement body)
    {
        var featureBody = body.TryGetProperty("feature", out var featureProp) ? featureProp : body;

        var flag = new FeatureFlag
        {
            Id = Guid.NewGuid(),
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
        };

        if (featureBody.TryGetProperty("name", out var nameProp))
        {
            flag.Name = nameProp.GetString() ?? string.Empty;
        }

        if (featureBody.TryGetProperty("description", out var descProp))
        {
            flag.Description = descProp.GetString();
        }

        if (featureBody.TryGetProperty("enabled", out var enabledProp))
        {
            flag.Enabled = enabledProp.GetBoolean();
        }

        if (featureBody.TryGetProperty("rollout_percentage", out var rolloutProp))
        {
            flag.RolloutPercentage = rolloutProp.GetInt32();
        }

        if (featureBody.TryGetProperty("expires_at", out var expiresProp) && expiresProp.ValueKind != JsonValueKind.Null)
        {
            flag.ExpiresAt = expiresProp.GetDateTime();
        }

        if (featureBody.TryGetProperty("target_users", out var targetUsersProp))
        {
            flag.TargetUsers = targetUsersProp.GetRawText();
        }

        if (featureBody.TryGetProperty("target_groups", out var targetGroupsProp))
        {
            flag.TargetGroups = targetGroupsProp.GetRawText();
        }

        var validationErrors = ValidateFeatureFlag(flag);
        if (validationErrors.Count > 0)
        {
            return UnprocessableEntity(new { error = "Validation failed", details = validationErrors });
        }

        var existing = await _context.FeatureFlags.AnyAsync(f => f.Name == flag.Name);
        if (existing)
        {
            return UnprocessableEntity(new { error = "Validation failed", details = new[] { "Name has already been taken" } });
        }

        _context.FeatureFlags.Add(flag);
        await _context.SaveChangesAsync();

        await _auditLogger.LogAsync(
            action: "feature_flag.created",
            resourceType: "FeatureFlag",
            resourceId: flag.Id,
            actorId: GetCurrentUserId(),
            actorEmail: GetCurrentUserEmail(),
            ipAddress: HttpContext.Connection.RemoteIpAddress?.ToString(),
            userAgent: Request.Headers.UserAgent.FirstOrDefault());

        return StatusCode(201, MapFeatureFlag(flag));
    }

    [HttpPut("{id:guid}")]
    public async Task<IActionResult> Update(Guid id, [FromBody] JsonElement body)
    {
        var flag = await _context.FeatureFlags.FindAsync(id);
        if (flag == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        var featureBody = body.TryGetProperty("feature", out var featureProp) ? featureProp : body;

        if (featureBody.TryGetProperty("name", out var nameProp))
        {
            flag.Name = nameProp.GetString() ?? flag.Name;
        }

        if (featureBody.TryGetProperty("description", out var descProp))
        {
            flag.Description = descProp.GetString();
        }

        if (featureBody.TryGetProperty("enabled", out var enabledProp))
        {
            flag.Enabled = enabledProp.GetBoolean();
        }

        if (featureBody.TryGetProperty("rollout_percentage", out var rolloutProp))
        {
            flag.RolloutPercentage = rolloutProp.GetInt32();
        }

        if (featureBody.TryGetProperty("expires_at", out var expiresProp))
        {
            flag.ExpiresAt = expiresProp.ValueKind == JsonValueKind.Null ? null : expiresProp.GetDateTime();
        }

        if (featureBody.TryGetProperty("target_users", out var targetUsersProp))
        {
            flag.TargetUsers = targetUsersProp.GetRawText();
        }

        if (featureBody.TryGetProperty("target_groups", out var targetGroupsProp))
        {
            flag.TargetGroups = targetGroupsProp.GetRawText();
        }

        flag.UpdatedAt = DateTime.UtcNow;

        var validationErrors = ValidateFeatureFlag(flag);
        if (validationErrors.Count > 0)
        {
            return UnprocessableEntity(new { error = "Validation failed", details = validationErrors });
        }

        await _context.SaveChangesAsync();

        await _auditLogger.LogAsync(
            action: "feature_flag.updated",
            resourceType: "FeatureFlag",
            resourceId: flag.Id,
            actorId: GetCurrentUserId(),
            actorEmail: GetCurrentUserEmail(),
            ipAddress: HttpContext.Connection.RemoteIpAddress?.ToString(),
            userAgent: Request.Headers.UserAgent.FirstOrDefault());

        return Ok(MapFeatureFlag(flag));
    }

    [HttpDelete("{id:guid}")]
    public async Task<IActionResult> Destroy(Guid id)
    {
        var flag = await _context.FeatureFlags.FindAsync(id);
        if (flag == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        _context.FeatureFlags.Remove(flag);
        await _context.SaveChangesAsync();

        await _auditLogger.LogAsync(
            action: "feature_flag.deleted",
            resourceType: "FeatureFlag",
            resourceId: flag.Id,
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

    private static List<string> ValidateFeatureFlag(FeatureFlag flag)
    {
        var errors = new List<string>();
        if (string.IsNullOrWhiteSpace(flag.Name))
        {
            errors.Add("Name can't be blank");
        }
        else if (!System.Text.RegularExpressions.Regex.IsMatch(flag.Name, @"^[a-z][a-z0-9_]*$"))
        {
            errors.Add("Name must be snake_case");
        }

        if (flag.RolloutPercentage < 0 || flag.RolloutPercentage > 100)
        {
            errors.Add("Rollout percentage must be between 0 and 100");
        }

        return errors;
    }

    private static FeatureFlagResponse MapFeatureFlag(FeatureFlag flag)
    {
        return new FeatureFlagResponse
        {
            Id = flag.Id,
            Name = flag.Name,
            Description = flag.Description,
            Enabled = flag.Enabled,
            TargetUsers = JsonSerializer.Deserialize<object>(flag.TargetUsers),
            TargetGroups = JsonSerializer.Deserialize<object>(flag.TargetGroups),
            RolloutPercentage = flag.RolloutPercentage,
            ExpiresAt = flag.ExpiresAt,
            Expired = flag.Expired,
            CreatedAt = flag.CreatedAt,
            UpdatedAt = flag.UpdatedAt,
        };
    }
}
