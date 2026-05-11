using System.Text.Json.Serialization;

namespace OtterWorks.AdminService.Models.Dto;

public class BulkUsersRequest
{
    [JsonPropertyName("operation")]
    public string Operation { get; set; } = string.Empty;

    [JsonPropertyName("user_ids")]
    public List<Guid> UserIds { get; set; } = [];

    [JsonPropertyName("reason")]
    public string? Reason { get; set; }

    [JsonPropertyName("role")]
    public string? Role { get; set; }
}

public class BulkUsersResponse
{
    [JsonPropertyName("operation")]
    public string Operation { get; set; } = string.Empty;

    [JsonPropertyName("success_count")]
    public int SuccessCount { get; set; }

    [JsonPropertyName("failure_count")]
    public int FailureCount { get; set; }

    [JsonPropertyName("errors")]
    public List<object> Errors { get; set; } = [];
}
