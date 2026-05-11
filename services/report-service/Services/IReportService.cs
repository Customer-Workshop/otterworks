using OtterWorks.ReportService.Models;

namespace OtterWorks.ReportService.Services;

public interface IReportService
{
    Task<Report> CreateReportAsync(ReportRequest request);
    Task<Report?> GetReportAsync(long id);
    Task<List<Report>> GetReportsByUserAsync(string userId);
    Task<List<Report>> GetReportsByStatusAsync(ReportStatus status);
    Task<bool> DeleteReportAsync(long id);
}
