using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models;
using OtterWorks.AdminService.Models.Dto;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Controllers;

[ApiController]
[Route("api/v1/admin/quotas")]
public class QuotasController : ControllerBase
{
    private readonly AdminDbContext _context;
    private readonly IAuditLogger _auditLogger;

    public QuotasController(AdminDbContext context, IAuditLogger auditLogger)
    {
        _context = context;
        _auditLogger = auditLogger;
    }

    [HttpGet("{userId:guid}")]
    public async Task<IActionResult> Show(Guid userId)
    {
        var quota = await _context.StorageQuotas.FirstOrDefaultAsync(q => q.UserId == userId);
        if (quota == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        return Ok(MapQuota(quota));
    }

    [HttpPut("{userId:guid}")]
    public async Task<IActionResult> Update(Guid userId, [FromBody] JsonElement body)
    {
        var quota = await _context.StorageQuotas.FirstOrDefaultAsync(q => q.UserId == userId);
        if (quota == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        var quotaBody = body.TryGetProperty("quota", out var quotaProp) ? quotaProp : body;
        var previousAttributes = new { quota.QuotaBytes, quota.Tier };

        if (quotaBody.TryGetProperty("quota_bytes", out var bytesProp))
        {
            quota.QuotaBytes = bytesProp.GetInt64();
        }

        if (quotaBody.TryGetProperty("tier", out var tierProp))
        {
            var newTier = tierProp.GetString();
            if (newTier != null && !StorageQuota.ValidTiers.Contains(newTier))
            {
                return UnprocessableEntity(new { error = "Validation failed", details = new[] { "Tier is not included in the list" } });
            }

            quota.Tier = newTier ?? quota.Tier;
        }

        var validationErrors = ValidateQuota(quota);
        if (validationErrors.Count > 0)
        {
            return UnprocessableEntity(new { error = "Validation failed", details = validationErrors });
        }

        quota.UpdatedAt = DateTime.UtcNow;
        await _context.SaveChangesAsync();

        await _auditLogger.LogAsync(
            action: "quota.updated",
            resourceType: "StorageQuota",
            resourceId: quota.Id,
            actorId: GetCurrentUserId(),
            actorEmail: GetCurrentUserEmail(),
            changesMade: new { before = previousAttributes, after = new { quota.QuotaBytes, quota.Tier } },
            ipAddress: HttpContext.Connection.RemoteIpAddress?.ToString(),
            userAgent: Request.Headers.UserAgent.FirstOrDefault());

        return Ok(MapQuota(quota));
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

    private static List<string> ValidateQuota(StorageQuota quota)
    {
        var errors = new List<string>();
        if (quota.QuotaBytes <= 0)
        {
            errors.Add("Quota bytes must be greater than 0");
        }

        if (quota.UsedBytes < 0)
        {
            errors.Add("Used bytes must be greater than or equal to 0");
        }

        if (!StorageQuota.ValidTiers.Contains(quota.Tier))
        {
            errors.Add("Tier is not included in the list");
        }

        return errors;
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
