namespace OtterWorks.AuditService.Services;

public interface IAuditArchiver
{
    Task<string> ExportToS3Async(DateTime startDate, DateTime endDate, string? userId);
}
