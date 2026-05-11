using OtterWorks.ReportService.Models;

namespace OtterWorks.ReportService.Data;

public interface IReportRepository
{
    Task<Report?> GetByIdAsync(long id);

    Task<List<Report>> GetByUserAsync(string userId);

    Task<List<Report>> GetByStatusAsync(ReportStatus status);

    Task<Report> AddAsync(Report report);

    Task<Report> UpdateAsync(Report report);

    Task<bool> DeleteAsync(long id);
}
