using OtterWorks.ReportService.Models;

namespace OtterWorks.ReportService.Repositories;

public interface IReportRepository
{
    Task<Report> CreateAsync(Report report);
    Task<Report?> GetByIdAsync(long id);
    Task<List<Report>> GetByUserAsync(string userId);
    Task<List<Report>> GetByStatusAsync(ReportStatus status);
    Task UpdateAsync(Report report);
    Task<bool> DeleteAsync(long id);
}
