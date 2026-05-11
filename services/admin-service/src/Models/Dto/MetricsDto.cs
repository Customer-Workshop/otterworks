using System.Text.Json.Serialization;

namespace OtterWorks.AdminService.Models.Dto;

public class MetricsSummaryResponse
{
    [JsonPropertyName("timestamp")]
    public string Timestamp { get; set; } = string.Empty;

    [JsonPropertyName("users")]
    public UserMetrics Users { get; set; } = new();

    [JsonPropertyName("storage")]
    public StorageMetrics Storage { get; set; } = new();

    [JsonPropertyName("features")]
    public FeatureMetrics Features { get; set; } = new();

    [JsonPropertyName("announcements")]
    public AnnouncementMetrics Announcements { get; set; } = new();

    [JsonPropertyName("audit")]
    public AuditMetrics Audit { get; set; } = new();
}

public class UserMetrics
{
    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("active")]
    public int Active { get; set; }

    [JsonPropertyName("suspended")]
    public int Suspended { get; set; }

    [JsonPropertyName("by_role")]
    public Dictionary<string, int> ByRole { get; set; } = new();

    [JsonPropertyName("recent_signups")]
    public int RecentSignups { get; set; }
}

public class StorageMetrics
{
    [JsonPropertyName("total_allocated_bytes")]
    public long TotalAllocatedBytes { get; set; }

    [JsonPropertyName("total_used_bytes")]
    public long TotalUsedBytes { get; set; }

    [JsonPropertyName("average_usage_percent")]
    public double AverageUsagePercent { get; set; }

    [JsonPropertyName("users_over_quota")]
    public int UsersOverQuota { get; set; }

    [JsonPropertyName("by_tier")]
    public Dictionary<string, int> ByTier { get; set; } = new();
}

public class FeatureMetrics
{
    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("enabled")]
    public int Enabled { get; set; }

    [JsonPropertyName("disabled")]
    public int Disabled { get; set; }
}

public class AnnouncementMetrics
{
    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("active")]
    public int Active { get; set; }

    [JsonPropertyName("by_severity")]
    public Dictionary<string, int> BySeverity { get; set; } = new();
}

public class AuditMetrics
{
    [JsonPropertyName("total_events")]
    public int TotalEvents { get; set; }

    [JsonPropertyName("events_today")]
    public int EventsToday { get; set; }

    [JsonPropertyName("events_this_week")]
    public int EventsThisWeek { get; set; }

    [JsonPropertyName("top_actions")]
    public Dictionary<string, int> TopActions { get; set; } = new();
}
