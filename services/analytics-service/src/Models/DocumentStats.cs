using System.Text.Json.Serialization;

namespace OtterWorks.AnalyticsService.Models;

public class DocumentStats
{
    [JsonPropertyName("documentId")]
    public string DocumentId { get; set; } = string.Empty;

    [JsonPropertyName("views")]
    public long Views { get; set; }

    [JsonPropertyName("edits")]
    public long Edits { get; set; }

    [JsonPropertyName("shares")]
    public long Shares { get; set; }

    [JsonPropertyName("uniqueViewers")]
    public long UniqueViewers { get; set; }

    [JsonPropertyName("lastViewedAt")]
    public string? LastViewedAt { get; set; }

    [JsonPropertyName("lastEditedAt")]
    public string? LastEditedAt { get; set; }
}
