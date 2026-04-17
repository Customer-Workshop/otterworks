namespace OtterWorks.AuditService.Services;

public interface IAuditRepository
{
    Task SaveEventAsync(AuditEvent auditEvent);
    Task<AuditEvent?> GetEventAsync(string id);
    Task<AuditEventPage> QueryEventsAsync(string? userId, string? action, string? resourceType, DateTime? from, DateTime? to, int page, int pageSize);
    Task<List<AuditEvent>> GetAllUserEventsAsync(string userId);
    Task<List<AuditEvent>> GetResourceHistoryAsync(string resourceId);
    Task<List<AuditEvent>> GetEventsByDateRangeAsync(DateTime from, DateTime to);
    Task DeleteEventsAsync(IEnumerable<string> eventIds);
}
