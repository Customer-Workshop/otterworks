using System.Text.Json.Serialization;

namespace OtterWorks.AdminService.Models.Dto;

public class StorageQuotaResponse
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; }

    [JsonPropertyName("user_id")]
    public Guid UserId { get; set; }

    [JsonPropertyName("quota_bytes")]
    public long QuotaBytes { get; set; }

    [JsonPropertyName("used_bytes")]
    public long UsedBytes { get; set; }

    [JsonPropertyName("tier")]
    public string Tier { get; set; } = string.Empty;

    [JsonPropertyName("usage_percentage")]
    public double UsagePercentage { get; set; }

    [JsonPropertyName("over_quota")]
    public bool OverQuota { get; set; }

    [JsonPropertyName("remaining_bytes")]
    public long RemainingBytes { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; set; }
}

public class UpdateQuotaRequest
{
    [JsonPropertyName("quota_bytes")]
    public long? QuotaBytes { get; set; }

    [JsonPropertyName("tier")]
    public string? Tier { get; set; }
}
