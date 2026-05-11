using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models;

namespace OtterWorks.AdminService.Services;

public interface IAuditLogger
{
    Task LogAsync(string action, string resourceType, Guid? resourceId = null, Guid? actorId = null, string? actorEmail = null, object? changesMade = null, string? ipAddress = null, string? userAgent = null);
}

public class AuditLogger : IAuditLogger
{
    private readonly AdminDbContext _context;
    private readonly ILogger<AuditLogger> _logger;

    public AuditLogger(AdminDbContext context, ILogger<AuditLogger> logger)
    {
        _context = context;
        _logger = logger;
    }

    public async Task LogAsync(string action, string resourceType, Guid? resourceId = null, Guid? actorId = null, string? actorEmail = null, object? changesMade = null, string? ipAddress = null, string? userAgent = null)
    {
        try
        {
            var auditLog = new AuditLog
            {
                Id = Guid.NewGuid(),
                Action = action,
                ResourceType = resourceType,
                ResourceId = resourceId,
                ActorId = actorId,
                ActorEmail = actorEmail,
                ChangesMade = changesMade != null ? System.Text.Json.JsonSerializer.Serialize(changesMade) : "{}",
                IpAddress = ipAddress,
                UserAgent = userAgent,
                CreatedAt = DateTime.UtcNow,
                UpdatedAt = DateTime.UtcNow,
            };

            _context.AuditLogs.Add(auditLog);
            await _context.SaveChangesAsync();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to record audit log");
        }
    }
}
