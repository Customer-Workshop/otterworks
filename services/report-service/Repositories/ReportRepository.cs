using Microsoft.EntityFrameworkCore;
using OtterWorks.ReportService.Data;
using OtterWorks.ReportService.Models;

namespace OtterWorks.ReportService.Repositories;

public class ReportRepository : IReportRepository
{
    private readonly ReportDbContext _context;

    public ReportRepository(ReportDbContext context)
    {
        _context = context;
    }

    public async Task<Report> CreateAsync(Report report)
    {
        _context.Reports.Add(report);
        await _context.SaveChangesAsync();
        return report;
    }

    public async Task<Report?> GetByIdAsync(long id)
    {
        return await _context.Reports.FindAsync(id);
    }

    public async Task<List<Report>> GetByUserAsync(string userId)
    {
        return await _context.Reports
            .Where(r => r.RequestedBy == userId)
            .OrderByDescending(r => r.CreatedAt)
            .ToListAsync();
    }

    public async Task<List<Report>> GetByStatusAsync(ReportStatus status)
    {
        return await _context.Reports
            .Where(r => r.Status == status)
            .OrderBy(r => r.CreatedAt)
            .ToListAsync();
    }

    public async Task UpdateAsync(Report report)
    {
        _context.Reports.Update(report);
        await _context.SaveChangesAsync();
    }

    public async Task<bool> DeleteAsync(long id)
    {
        var report = await _context.Reports.FindAsync(id);
        if (report == null)
        {
            return false;
        }

        _context.Reports.Remove(report);
        await _context.SaveChangesAsync();
        return true;
    }
}
