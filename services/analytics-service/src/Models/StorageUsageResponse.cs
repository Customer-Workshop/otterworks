using System.Text.Json.Serialization;

namespace OtterWorks.AnalyticsService.Models;

public class StorageUsageResponse
{
    [JsonPropertyName("userId")]
    public string? UserId { get; set; }

    [JsonPropertyName("totalStorageBytes")]
    public long TotalStorageBytes { get; set; }

    [JsonPropertyName("filesCount")]
    public long FilesCount { get; set; }

    [JsonPropertyName("documentsCount")]
    public long DocumentsCount { get; set; }

    [JsonPropertyName("breakdownByType")]
    public Dictionary<string, long> BreakdownByType { get; set; } = new();
}
