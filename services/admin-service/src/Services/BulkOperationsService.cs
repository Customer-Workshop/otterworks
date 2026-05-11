using Microsoft.EntityFrameworkCore;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models;

namespace OtterWorks.AdminService.Services;

public class BulkResult
{
    public int SuccessCount { get; set; }
    public int FailureCount { get; set; }
    public List<object> Errors { get; set; } = [];
}

public interface IBulkOperationsService
{
    Task<BulkResult> ProcessAsync(string operation, List<Guid> userIds, string? reason = null, string? role = null);
}

public class BulkOperationsService : IBulkOperationsService
{
    private static readonly string[] ValidOperations = ["suspend", "activate", "delete", "update_role"];

    private readonly AdminDbContext _context;
    private readonly IAuditLogger _auditLogger;

    public BulkOperationsService(AdminDbContext context, IAuditLogger auditLogger)
    {
        _context = context;
        _auditLogger = auditLogger;
    }

    public async Task<BulkResult> ProcessAsync(string operation, List<Guid> userIds, string? reason = null, string? role = null)
    {
        if (!ValidOperations.Contains(operation))
        {
            return new BulkResult { Errors = [new { error = $"Invalid operation: {operation}" }] };
        }

        var users = await _context.AdminUsers.Where(u => userIds.Contains(u.Id)).ToListAsync();
        var successCount = 0;
        var failureCount = 0;
        var errors = new List<object>();

        foreach (var user in users)
        {
            try
            {
                ApplyOperation(user, operation, reason, role);
                successCount++;
            }
            catch (Exception ex)
            {
                failureCount++;
                errors.Add(new { user_id = user.Id, error = ex.Message });
            }
        }

        var missingCount = userIds.Distinct().Count() - users.Count;
        if (missingCount > 0)
        {
            failureCount += missingCount;
            errors.Add(new { error = $"{missingCount} user(s) not found" });
        }

        await _context.SaveChangesAsync();

        await _auditLogger.LogAsync(
            action: "bulk.users_updated",
            resourceType: "AdminUser",
            changesMade: new { operation, user_ids = userIds, success = successCount, failures = failureCount });

        return new BulkResult { SuccessCount = successCount, FailureCount = failureCount, Errors = errors };
    }

    private static void ApplyOperation(AdminUser user, string operation, string? reason, string? role)
    {
        switch (operation)
        {
            case "suspend":
                user.Suspend(reason);
                break;
            case "activate":
                user.Activate();
                break;
            case "delete":
                user.SoftDelete();
                break;
            case "update_role":
                if (string.IsNullOrEmpty(role) || !AdminUser.ValidRoles.Contains(role))
                {
                    throw new InvalidOperationException($"Invalid role: {role}");
                }

                user.Role = role;
                user.UpdatedAt = DateTime.UtcNow;
                break;
        }
    }
}
