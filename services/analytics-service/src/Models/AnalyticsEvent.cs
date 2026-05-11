using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.AnalyticsService.Models;

[Table("analytics_events")]
public class AnalyticsEvent
{
    [Key]
    [Column("event_id")]
    public string EventId { get; set; } = string.Empty;

    [Required]
    [Column("event_type")]
    public string EventType { get; set; } = string.Empty;

    [Required]
    [Column("user_id")]
    public string UserId { get; set; } = string.Empty;

    [Required]
    [Column("resource_id")]
    public string ResourceId { get; set; } = string.Empty;

    [Required]
    [Column("resource_type")]
    public string ResourceType { get; set; } = string.Empty;

    [Column("metadata", TypeName = "jsonb")]
    public Dictionary<string, string> Metadata { get; set; } = new();

    [Column("timestamp")]
    public DateTime Timestamp { get; set; } = DateTime.UtcNow;

    public static AnalyticsEvent Create(
        string eventType,
        string userId,
        string resourceId,
        string resourceType,
        Dictionary<string, string>? metadata = null)
    {
        return new AnalyticsEvent
        {
            EventId = Guid.NewGuid().ToString(),
            EventType = eventType,
            UserId = userId,
            ResourceId = resourceId,
            ResourceType = resourceType,
            Metadata = metadata ?? new Dictionary<string, string>(),
            Timestamp = DateTime.UtcNow,
        };
    }
}
