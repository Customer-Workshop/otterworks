using OtterWorks.AnalyticsService.Models;

namespace OtterWorks.AnalyticsService.Services;

public class InMemoryMetricsRepository : IMetricsRepository
{
    private readonly List<AnalyticsEvent> _events = new();
    private readonly object _lock = new();

    public Task StoreEventAsync(AnalyticsEvent analyticsEvent)
    {
        lock (_lock)
        {
            _events.Add(analyticsEvent);
        }

        return Task.CompletedTask;
    }

    public Task<DashboardSummary> GetDashboardSummaryAsync(string period)
    {
        var cutoff = PeriodToCutoff(period);
        lock (_lock)
        {
            var filtered = _events.Where(e => e.Timestamp > cutoff).ToList();
            var storageBytes = _events
                .Where(e => e.EventType == EventTypes.StorageAllocated || e.EventType == EventTypes.StorageReleased)
                .Aggregate(0L, (acc, e) =>
                {
                    var bytes = e.Metadata.TryGetValue("bytes", out var b) && long.TryParse(b, out var v) ? v : 0L;
                    return e.EventType == EventTypes.StorageAllocated ? acc + bytes : acc - bytes;
                });

            return Task.FromResult(new DashboardSummary
            {
                Period = period,
                DailyActiveUsers = filtered.Select(e => e.UserId).Distinct().Count(),
                DocumentsCreated = filtered.Count(e => e.EventType == EventTypes.DocumentCreated),
                FilesUploaded = filtered.Count(e => e.EventType == EventTypes.FileUploaded),
                StorageUsedBytes = Math.Max(0L, storageBytes),
                CollabSessions = filtered.Count(e => e.EventType == EventTypes.CollabSessionStarted),
                TotalEvents = filtered.Count,
            });
        }
    }

    public Task<UserActivity> GetUserActivityAsync(string userId)
    {
        lock (_lock)
        {
            var userEvents = _events.Where(e => e.UserId == userId).ToList();
            var recent = userEvents.OrderByDescending(e => e.Timestamp).Take(20).ToList();

            return Task.FromResult(new UserActivity
            {
                UserId = userId,
                TotalEvents = userEvents.Count,
                DocumentsCreated = userEvents.Count(e => e.EventType == EventTypes.DocumentCreated),
                DocumentsViewed = userEvents.Count(e => e.EventType == EventTypes.DocumentViewed),
                DocumentsEdited = userEvents.Count(e => e.EventType == EventTypes.DocumentEdited),
                FilesUploaded = userEvents.Count(e => e.EventType == EventTypes.FileUploaded),
                FilesDownloaded = userEvents.Count(e => e.EventType == EventTypes.FileDownloaded),
                LastActiveAt = recent.FirstOrDefault()?.Timestamp.ToString("o"),
                RecentEvents = recent.Select(e => new EventSummary
                {
                    EventId = e.EventId,
                    EventType = e.EventType,
                    ResourceId = e.ResourceId,
                    ResourceType = e.ResourceType,
                    Timestamp = e.Timestamp.ToString("o"),
                }).ToList(),
            });
        }
    }

    public Task<DocumentStats> GetDocumentStatsAsync(string documentId)
    {
        lock (_lock)
        {
            var docEvents = _events.Where(e => e.ResourceId == documentId).ToList();
            var views = docEvents.Where(e => e.EventType == EventTypes.DocumentViewed).ToList();
            var edits = docEvents.Where(e => e.EventType == EventTypes.DocumentEdited).ToList();
            var shares = docEvents.Where(e => e.EventType == EventTypes.DocumentShared).ToList();

            return Task.FromResult(new DocumentStats
            {
                DocumentId = documentId,
                Views = views.Count,
                Edits = edits.Count,
                Shares = shares.Count,
                UniqueViewers = views.Select(e => e.UserId).Distinct().Count(),
                LastViewedAt = views.OrderByDescending(e => e.Timestamp).FirstOrDefault()?.Timestamp.ToString("o"),
                LastEditedAt = edits.OrderByDescending(e => e.Timestamp).FirstOrDefault()?.Timestamp.ToString("o"),
            });
        }
    }

    public Task<TopContentResponse> GetTopContentAsync(string contentType, string period, int limit)
    {
        var cutoff = PeriodToCutoff(period);
        lock (_lock)
        {
            var resourceTypeFilter = contentType switch
            {
                "documents" => new HashSet<string> { "document" },
                "files" => new HashSet<string> { "file" },
                _ => new HashSet<string> { "document", "file" },
            };

            var filtered = _events
                .Where(e => e.Timestamp > cutoff && resourceTypeFilter.Contains(e.ResourceType))
                .ToList();

            var items = filtered
                .GroupBy(e => e.ResourceId)
                .Select(g => new ContentItem
                {
                    ResourceId = g.Key,
                    ResourceType = g.First().ResourceType,
                    Title = g.First().Metadata.TryGetValue("title", out var t) ? t : g.Key,
                    EventCount = g.Count(),
                    UniqueUsers = g.Select(e => e.UserId).Distinct().Count(),
                })
                .OrderByDescending(i => i.EventCount)
                .Take(limit)
                .ToList();

            return Task.FromResult(new TopContentResponse
            {
                Period = period,
                ContentType = contentType,
                Items = items,
            });
        }
    }

    public Task<ActiveUsersResponse> GetActiveUsersAsync(string period)
    {
        var cutoff = PeriodToCutoff(period);
        lock (_lock)
        {
            var filtered = _events.Where(e => e.Timestamp > cutoff).ToList();
            var users = filtered
                .GroupBy(e => e.UserId)
                .Select(g => new ActiveUser
                {
                    UserId = g.Key,
                    EventCount = g.Count(),
                    LastActiveAt = g.Max(e => e.Timestamp).ToString("o"),
                })
                .OrderByDescending(u => u.EventCount)
                .ToList();

            return Task.FromResult(new ActiveUsersResponse
            {
                Period = period,
                Count = users.Count,
                Users = users,
            });
        }
    }

    public Task<StorageUsageResponse> GetStorageUsageAsync(string? userId)
    {
        lock (_lock)
        {
            var filtered = userId != null
                ? _events.Where(e => e.UserId == userId).ToList()
                : _events.ToList();

            var storageEvents = filtered
                .Where(e => e.EventType == EventTypes.StorageAllocated || e.EventType == EventTypes.StorageReleased)
                .ToList();

            var totalBytes = storageEvents.Aggregate(0L, (acc, e) =>
            {
                var bytes = e.Metadata.TryGetValue("bytes", out var b) && long.TryParse(b, out var v) ? v : 0L;
                return e.EventType == EventTypes.StorageAllocated ? acc + bytes : acc - bytes;
            });

            var breakdownByType = filtered
                .Where(e => e.EventType == EventTypes.StorageAllocated)
                .GroupBy(e => e.ResourceType)
                .ToDictionary(
                    g => g.Key,
                    g => g.Sum(e => e.Metadata.TryGetValue("bytes", out var b) && long.TryParse(b, out var v) ? v : 0L));

            return Task.FromResult(new StorageUsageResponse
            {
                UserId = userId,
                TotalStorageBytes = Math.Max(0L, totalBytes),
                FilesCount = filtered.Count(e => e.EventType == EventTypes.FileUploaded),
                DocumentsCount = filtered.Count(e => e.EventType == EventTypes.DocumentCreated),
                BreakdownByType = breakdownByType,
            });
        }
    }

    public Task<List<Dictionary<string, string>>> GetExportDataAsync(string period)
    {
        var cutoff = PeriodToCutoff(period);
        lock (_lock)
        {
            var data = _events
                .Where(e => e.Timestamp > cutoff)
                .OrderByDescending(e => e.Timestamp)
                .Select(e => new Dictionary<string, string>
                {
                    ["event_id"] = e.EventId,
                    ["event_type"] = e.EventType,
                    ["user_id"] = e.UserId,
                    ["resource_id"] = e.ResourceId,
                    ["resource_type"] = e.ResourceType,
                    ["timestamp"] = e.Timestamp.ToString("o"),
                })
                .ToList();

            return Task.FromResult(data);
        }
    }

    public Task<long> GetEventCountAsync()
    {
        lock (_lock)
        {
            return Task.FromResult((long)_events.Count);
        }
    }

    private static DateTime PeriodToCutoff(string period)
    {
        var now = DateTime.UtcNow;
        return period switch
        {
            "7d" => now.AddDays(-7),
            "30d" => now.AddDays(-30),
            "90d" => now.AddDays(-90),
            "daily" => now.AddDays(-1),
            "weekly" => now.AddDays(-7),
            "monthly" => now.AddDays(-30),
            _ => now.AddDays(-7),
        };
    }
}
