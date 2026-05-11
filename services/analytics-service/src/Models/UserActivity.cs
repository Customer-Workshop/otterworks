using System.Text.Json.Serialization;

namespace OtterWorks.AnalyticsService.Models;

public class UserActivity
{
    [JsonPropertyName("userId")]
    public string UserId { get; set; } = string.Empty;

    [JsonPropertyName("totalEvents")]
    public long TotalEvents { get; set; }

    [JsonPropertyName("documentsCreated")]
    public long DocumentsCreated { get; set; }

    [JsonPropertyName("documentsViewed")]
    public long DocumentsViewed { get; set; }

    [JsonPropertyName("documentsEdited")]
    public long DocumentsEdited { get; set; }

    [JsonPropertyName("filesUploaded")]
    public long FilesUploaded { get; set; }

    [JsonPropertyName("filesDownloaded")]
    public long FilesDownloaded { get; set; }

    [JsonPropertyName("lastActiveAt")]
    public string? LastActiveAt { get; set; }

    [JsonPropertyName("recentEvents")]
    public List<EventSummary> RecentEvents { get; set; } = new();
}

public class EventSummary
{
    [JsonPropertyName("eventId")]
    public string EventId { get; set; } = string.Empty;

    [JsonPropertyName("eventType")]
    public string EventType { get; set; } = string.Empty;

    [JsonPropertyName("resourceId")]
    public string ResourceId { get; set; } = string.Empty;

    [JsonPropertyName("resourceType")]
    public string ResourceType { get; set; } = string.Empty;

    [JsonPropertyName("timestamp")]
    public string Timestamp { get; set; } = string.Empty;
}
