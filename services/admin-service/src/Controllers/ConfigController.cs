using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models.Dto;
using OtterWorks.AdminService.Services;

namespace OtterWorks.AdminService.Controllers;

[ApiController]
[Route("api/v1/admin/config")]
public class ConfigController : ControllerBase
{
    private readonly AdminDbContext _context;
    private readonly IAuditLogger _auditLogger;

    public ConfigController(AdminDbContext context, IAuditLogger auditLogger)
    {
        _context = context;
        _auditLogger = auditLogger;
    }

    [HttpGet]
    public async Task<IActionResult> Index()
    {
        var configs = await _context.SystemConfigs
            .Where(c => !c.IsSecret)
            .OrderBy(c => c.Key)
            .ToListAsync();

        return Ok(new SystemConfigsListResponse
        {
            Configs = configs.Select(c => MapConfig(c)).ToList(),
        });
    }

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> Show(Guid id)
    {
        var config = await _context.SystemConfigs.FindAsync(id);
        if (config == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        return Ok(MapConfig(config));
    }

    [HttpPut("{id:guid}")]
    public async Task<IActionResult> Update(Guid id, [FromBody] JsonElement body)
    {
        var config = await _context.SystemConfigs.FindAsync(id);
        if (config == null)
        {
            return NotFound(new { error = "Resource not found" });
        }

        var configBody = body.TryGetProperty("config", out var configProp) ? configProp : body;
        var previousValue = config.IsSecret ? "********" : config.Value;

        if (configBody.TryGetProperty("value", out var valueProp))
        {
            var newValue = valueProp.GetString();
            if (string.IsNullOrEmpty(newValue))
            {
                return UnprocessableEntity(new { error = "Validation failed", details = new[] { "Value can't be blank" } });
            }

            config.Value = newValue;
        }

        if (configBody.TryGetProperty("description", out var descProp))
        {
            config.Description = descProp.GetString();
        }

        config.UpdatedAt = DateTime.UtcNow;
        await _context.SaveChangesAsync();

        var afterValue = config.IsSecret ? "********" : config.Value;
        await _auditLogger.LogAsync(
            action: "config.updated",
            resourceType: "SystemConfig",
            resourceId: config.Id,
            actorId: GetCurrentUserId(),
            actorEmail: GetCurrentUserEmail(),
            changesMade: new { key = config.Key, before = previousValue, after = afterValue },
            ipAddress: HttpContext.Connection.RemoteIpAddress?.ToString(),
            userAgent: Request.Headers.UserAgent.FirstOrDefault());

        return Ok(MapConfig(config));
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

    private static SystemConfigResponse MapConfig(Models.SystemConfig config)
    {
        return new SystemConfigResponse
        {
            Id = config.Id,
            Key = config.Key,
            Value = config.IsSecret ? "********" : config.Value,
            ValueType = config.ValueType,
            Description = config.Description,
            IsSecret = config.IsSecret,
            CreatedAt = config.CreatedAt,
            UpdatedAt = config.UpdatedAt,
        };
    }
}
