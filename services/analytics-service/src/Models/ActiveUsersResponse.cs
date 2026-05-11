using System.Text.Json.Serialization;

namespace OtterWorks.AnalyticsService.Models;

public class ActiveUsersResponse
{
    [JsonPropertyName("period")]
    public string Period { get; set; } = string.Empty;

    [JsonPropertyName("count")]
    public long Count { get; set; }

    [JsonPropertyName("users")]
    public List<ActiveUser> Users { get; set; } = new();
}

public class ActiveUser
{
    [JsonPropertyName("userId")]
    public string UserId { get; set; } = string.Empty;

    [JsonPropertyName("eventCount")]
    public long EventCount { get; set; }

    [JsonPropertyName("lastActiveAt")]
    public string LastActiveAt { get; set; } = string.Empty;
}
