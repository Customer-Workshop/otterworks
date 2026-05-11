using System.Text.Json.Serialization;

namespace OtterWorks.AnalyticsService.Models;

public class TopContentResponse
{
    [JsonPropertyName("period")]
    public string Period { get; set; } = string.Empty;

    [JsonPropertyName("contentType")]
    public string ContentType { get; set; } = string.Empty;

    [JsonPropertyName("items")]
    public List<ContentItem> Items { get; set; } = new();
}

public class ContentItem
{
    [JsonPropertyName("resourceId")]
    public string ResourceId { get; set; } = string.Empty;

    [JsonPropertyName("resourceType")]
    public string ResourceType { get; set; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("eventCount")]
    public long EventCount { get; set; }

    [JsonPropertyName("uniqueUsers")]
    public long UniqueUsers { get; set; }
}
