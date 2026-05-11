using Microsoft.EntityFrameworkCore;
using OtterWorks.AdminService.Data;
using OtterWorks.AdminService.Models.Dto;

namespace OtterWorks.AdminService.Services;

public interface IMetricsAggregator
{
    Task<MetricsSummaryResponse> GetSummaryAsync();
}

public class MetricsAggregator : IMetricsAggregator
{
    private readonly AdminDbContext _context;

    public MetricsAggregator(AdminDbContext context)
    {
        _context = context;
    }

    public async Task<MetricsSummaryResponse> GetSummaryAsync()
    {
        return new MetricsSummaryResponse
        {
            Timestamp = DateTime.UtcNow.ToString("o"),
            Users = await GetUserMetricsAsync(),
            Storage = await GetStorageMetricsAsync(),
            Features = await GetFeatureMetricsAsync(),
            Announcements = await GetAnnouncementMetricsAsync(),
            Audit = await GetAuditMetricsAsync(),
        };
    }

    private async Task<UserMetrics> GetUserMetricsAsync()
    {
        var thirtyDaysAgo = DateTime.UtcNow.AddDays(-30);
        return new UserMetrics
        {
            Total = await _context.AdminUsers.CountAsync(),
            Active = await _context.AdminUsers.CountAsync(u => u.Status == "active"),
            Suspended = await _context.AdminUsers.CountAsync(u => u.Status == "suspended"),
            ByRole = (await _context.AdminUsers.ToListAsync()).GroupBy(u => u.Role).ToDictionary(g => g.Key, g => g.Count()),
            RecentSignups = await _context.AdminUsers.CountAsync(u => u.CreatedAt >= thirtyDaysAgo),
        };
    }

    private async Task<StorageMetrics> GetStorageMetricsAsync()
    {
        var quotas = _context.StorageQuotas;
        var totalAllocated = await quotas.SumAsync(q => q.QuotaBytes);
        var totalUsed = await quotas.SumAsync(q => q.UsedBytes);
        var count = await quotas.CountAsync();
        var avgUsage = count == 0 ? 0 : await quotas.Where(q => q.QuotaBytes > 0).AverageAsync(q => (double)q.UsedBytes / q.QuotaBytes * 100);

        return new StorageMetrics
        {
            TotalAllocatedBytes = totalAllocated,
            TotalUsedBytes = totalUsed,
            AverageUsagePercent = Math.Round(avgUsage, 2),
            UsersOverQuota = await quotas.CountAsync(q => q.UsedBytes >= q.QuotaBytes),
            ByTier = (await quotas.ToListAsync()).GroupBy(q => q.Tier).ToDictionary(g => g.Key, g => g.Count()),
        };
    }

    private async Task<FeatureMetrics> GetFeatureMetricsAsync()
    {
        return new FeatureMetrics
        {
            Total = await _context.FeatureFlags.CountAsync(),
            Enabled = await _context.FeatureFlags.CountAsync(f => f.Enabled),
            Disabled = await _context.FeatureFlags.CountAsync(f => !f.Enabled),
        };
    }

    private async Task<AnnouncementMetrics> GetAnnouncementMetricsAsync()
    {
        var now = DateTime.UtcNow;
        return new AnnouncementMetrics
        {
            Total = await _context.Announcements.CountAsync(),
            Active = await _context.Announcements.CountAsync(a =>
                a.Status == "published" &&
                (!a.StartsAt.HasValue || a.StartsAt <= now) &&
                (!a.EndsAt.HasValue || a.EndsAt >= now)),
            BySeverity = (await _context.Announcements.ToListAsync()).GroupBy(a => a.Severity).ToDictionary(g => g.Key, g => g.Count()),
        };
    }

    private async Task<AuditMetrics> GetAuditMetricsAsync()
    {
        var today = DateTime.UtcNow.Date;
        var oneWeekAgo = DateTime.UtcNow.AddDays(-7);

        return new AuditMetrics
        {
            TotalEvents = await _context.AuditLogs.CountAsync(),
            EventsToday = await _context.AuditLogs.CountAsync(l => l.CreatedAt >= today),
            EventsThisWeek = await _context.AuditLogs.CountAsync(l => l.CreatedAt >= oneWeekAgo),
            TopActions = (await _context.AuditLogs
                .Where(l => l.CreatedAt >= oneWeekAgo)
                .ToListAsync())
                .GroupBy(l => l.Action)
                .OrderByDescending(g => g.Count())
                .Take(5)
                .ToDictionary(g => g.Key, g => g.Count()),
        };
    }
}
