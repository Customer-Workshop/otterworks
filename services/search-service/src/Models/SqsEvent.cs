using System.Text.Json.Serialization;

namespace OtterWorks.SearchService.Models;

public class SqsEvent
{
    [JsonPropertyName("action")]
    public string? Action { get; set; }

    [JsonPropertyName("data")]
    public Dictionary<string, object>? Data { get; set; }

    [JsonPropertyName("event_type")]
    public string? EventType { get; set; }

    [JsonPropertyName("payload")]
    public Dictionary<string, object>? Payload { get; set; }

    [JsonPropertyName("eventType")]
    public string? CamelEventType { get; set; }

    [JsonPropertyName("fileId")]
    public string? FileId { get; set; }

    [JsonPropertyName("name")]
    public string? Name { get; set; }

    [JsonPropertyName("mimeType")]
    public string? MimeType { get; set; }

    [JsonPropertyName("ownerId")]
    public string? OwnerId { get; set; }

    [JsonPropertyName("folderId")]
    public string? FolderId { get; set; }

    [JsonPropertyName("sizeBytes")]
    public int? SizeBytes { get; set; }

    [JsonPropertyName("tags")]
    public List<string>? EventTags { get; set; }

    [JsonPropertyName("timestamp")]
    public string? Timestamp { get; set; }

    [JsonPropertyName("Message")]
    public string? SnsMessage { get; set; }

    [JsonPropertyName("TopicArn")]
    public string? TopicArn { get; set; }
}
