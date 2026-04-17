using OtterWorks.AuditService.Models;

namespace OtterWorks.AuditService.Services;

public interface IAuditArchiver
{
    Task<ExportResult> ExportAsync(DateTime from, DateTime to, string format);
    Task<ArchiveResult> ArchiveOldEventsAsync(DateTime olderThan);
}
