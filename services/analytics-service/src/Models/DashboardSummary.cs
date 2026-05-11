using System.Text.Json.Serialization;

namespace OtterWorks.AnalyticsService.Models;

public class DashboardSummary
{
    [JsonPropertyName("period")]
    public string Period { get; set; } = string.Empty;

    [JsonPropertyName("dailyActiveUsers")]
    public long DailyActiveUsers { get; set; }

    [JsonPropertyName("documentsCreated")]
    public long DocumentsCreated { get; set; }

    [JsonPropertyName("filesUploaded")]
    public long FilesUploaded { get; set; }

    [JsonPropertyName("storageUsedBytes")]
    public long StorageUsedBytes { get; set; }

    [JsonPropertyName("collabSessions")]
    public long CollabSessions { get; set; }

    [JsonPropertyName("totalEvents")]
    public long TotalEvents { get; set; }
}
