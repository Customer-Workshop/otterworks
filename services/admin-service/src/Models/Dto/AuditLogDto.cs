using System.Text.Json.Serialization;

namespace OtterWorks.AdminService.Models.Dto;

public class AuditLogResponse
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; }

    [JsonPropertyName("actor_id")]
    public Guid? ActorId { get; set; }

    [JsonPropertyName("actor_email")]
    public string? ActorEmail { get; set; }

    [JsonPropertyName("action")]
    public string Action { get; set; } = string.Empty;

    [JsonPropertyName("resource_type")]
    public string ResourceType { get; set; } = string.Empty;

    [JsonPropertyName("resource_id")]
    public Guid? ResourceId { get; set; }

    [JsonPropertyName("changes_made")]
    public object? ChangesMade { get; set; }

    [JsonPropertyName("ip_address")]
    public string? IpAddress { get; set; }

    [JsonPropertyName("user_agent")]
    public string? UserAgent { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }
}

public class AuditLogsListResponse
{
    [JsonPropertyName("audit_logs")]
    public List<AuditLogResponse> AuditLogs { get; set; } = [];

    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("page")]
    public int Page { get; set; }

    [JsonPropertyName("per_page")]
    public int PerPage { get; set; }
}
