using System.Text.Json.Serialization;

namespace OtterWorks.AnalyticsService.Models;

public class AcceptedResponse
{
    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("eventId")]
    public string EventId { get; set; } = string.Empty;
}
