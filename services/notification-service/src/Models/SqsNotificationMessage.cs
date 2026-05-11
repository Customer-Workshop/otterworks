using System.Text.Json.Serialization;

namespace OtterWorks.NotificationService.Models;

public class SqsNotificationMessage
{
    [JsonPropertyName("eventType")]
    public string EventType { get; set; } = string.Empty;

    [JsonPropertyName("fileId")]
    public string FileId { get; set; } = string.Empty;

    [JsonPropertyName("ownerId")]
    public string OwnerId { get; set; } = string.Empty;

    [JsonPropertyName("sharedWithUserId")]
    public string SharedWithUserId { get; set; } = string.Empty;

    [JsonPropertyName("documentId")]
    public string DocumentId { get; set; } = string.Empty;

    [JsonPropertyName("commentId")]
    public string CommentId { get; set; } = string.Empty;

    [JsonPropertyName("userId")]
    public string UserId { get; set; } = string.Empty;

    [JsonPropertyName("actorId")]
    public string ActorId { get; set; } = string.Empty;

    [JsonPropertyName("mentionedUserId")]
    public string MentionedUserId { get; set; } = string.Empty;

    [JsonPropertyName("timestamp")]
    public string Timestamp { get; set; } = string.Empty;
}
