using System.Text.Json.Serialization;

namespace OtterWorks.AdminService.Models.Dto;

public class FeatureFlagResponse
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; }

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string? Description { get; set; }

    [JsonPropertyName("enabled")]
    public bool Enabled { get; set; }

    [JsonPropertyName("target_users")]
    public object? TargetUsers { get; set; }

    [JsonPropertyName("target_groups")]
    public object? TargetGroups { get; set; }

    [JsonPropertyName("rollout_percentage")]
    public int RolloutPercentage { get; set; }

    [JsonPropertyName("expires_at")]
    public DateTime? ExpiresAt { get; set; }

    [JsonPropertyName("expired")]
    public bool Expired { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; set; }
}

public class CreateFeatureFlagRequest
{
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    [JsonPropertyName("description")]
    public string? Description { get; set; }

    [JsonPropertyName("enabled")]
    public bool Enabled { get; set; }

    [JsonPropertyName("rollout_percentage")]
    public int RolloutPercentage { get; set; }

    [JsonPropertyName("expires_at")]
    public DateTime? ExpiresAt { get; set; }

    [JsonPropertyName("target_users")]
    public List<string>? TargetUsers { get; set; }

    [JsonPropertyName("target_groups")]
    public List<string>? TargetGroups { get; set; }
}

public class UpdateFeatureFlagRequest
{
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    [JsonPropertyName("description")]
    public string? Description { get; set; }

    [JsonPropertyName("enabled")]
    public bool? Enabled { get; set; }

    [JsonPropertyName("rollout_percentage")]
    public int? RolloutPercentage { get; set; }

    [JsonPropertyName("expires_at")]
    public DateTime? ExpiresAt { get; set; }

    [JsonPropertyName("target_users")]
    public List<string>? TargetUsers { get; set; }

    [JsonPropertyName("target_groups")]
    public List<string>? TargetGroups { get; set; }
}

public class FeatureFlagsListResponse
{
    [JsonPropertyName("features")]
    public List<FeatureFlagResponse> Features { get; set; } = [];

    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("page")]
    public int Page { get; set; }

    [JsonPropertyName("per_page")]
    public int PerPage { get; set; }
}
