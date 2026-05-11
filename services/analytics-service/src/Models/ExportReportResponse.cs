using System.Text.Json.Serialization;

namespace OtterWorks.AnalyticsService.Models;

public class ExportReportResponse
{
    [JsonPropertyName("format")]
    public string Format { get; set; } = string.Empty;

    [JsonPropertyName("period")]
    public string Period { get; set; } = string.Empty;

    [JsonPropertyName("generatedAt")]
    public string GeneratedAt { get; set; } = string.Empty;

    [JsonPropertyName("recordCount")]
    public long RecordCount { get; set; }

    [JsonPropertyName("data")]
    public List<Dictionary<string, string>> Data { get; set; } = new();
}
