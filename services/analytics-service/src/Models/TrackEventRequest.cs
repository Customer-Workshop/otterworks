using System.Text.Json.Serialization;

namespace OtterWorks.AnalyticsService.Models;

public class TrackEventRequest
{
    [JsonPropertyName("eventType")]
    public string EventType { get; set; } = string.Empty;

    [JsonPropertyName("userId")]
    public string UserId { get; set; } = string.Empty;

    [JsonPropertyName("resourceId")]
    public string ResourceId { get; set; } = string.Empty;

    [JsonPropertyName("resourceType")]
    public string ResourceType { get; set; } = string.Empty;

    [JsonPropertyName("metadata")]
    public Dictionary<string, string>? Metadata { get; set; }
}
