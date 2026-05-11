using System.Text.Json.Serialization;

namespace OtterWorks.NotificationService.Models;

public class PaginatedResponse<T>
{
    [JsonPropertyName("data")]
    public List<T> Data { get; set; } = new();

    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("page")]
    public int Page { get; set; }

    [JsonPropertyName("pageSize")]
    public int PageSize { get; set; }

    [JsonPropertyName("hasMore")]
    public bool HasMore { get; set; }
}

public class UnreadCountResponse
{
    [JsonPropertyName("userId")]
    public string UserId { get; set; } = string.Empty;

    [JsonPropertyName("unreadCount")]
    public int UnreadCount { get; set; }
}

public class HealthResponse
{
    [JsonPropertyName("status")]
    public string Status { get; set; } = "healthy";

    [JsonPropertyName("service")]
    public string Service { get; set; } = "notification-service";

    [JsonPropertyName("version")]
    public string Version { get; set; } = "0.1.0";
}

public class ErrorResponse
{
    [JsonPropertyName("error")]
    public string Error { get; set; } = string.Empty;
}

public class MarkAllReadResponse
{
    [JsonPropertyName("markedCount")]
    public int MarkedCount { get; set; }
}

public class NotificationPreferenceRequest
{
    [JsonPropertyName("userId")]
    public string UserId { get; set; } = string.Empty;

    [JsonPropertyName("eventType")]
    public string EventType { get; set; } = string.Empty;

    [JsonPropertyName("channels")]
    public List<DeliveryChannel> Channels { get; set; } = new();
}

public class SnsEnvelope
{
    [JsonPropertyName("Message")]
    public string Message { get; set; } = string.Empty;

    [JsonPropertyName("MessageId")]
    public string MessageId { get; set; } = string.Empty;

    [JsonPropertyName("TopicArn")]
    public string TopicArn { get; set; } = string.Empty;

    [JsonPropertyName("Type")]
    public string Type { get; set; } = string.Empty;
}
