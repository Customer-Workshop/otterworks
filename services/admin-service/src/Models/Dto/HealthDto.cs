using System.Text.Json.Serialization;

namespace OtterWorks.AdminService.Models.Dto;

public class HealthResponse
{
    [JsonPropertyName("status")]
    public string Status { get; set; } = "healthy";

    [JsonPropertyName("service")]
    public string Service { get; set; } = "admin-service";

    [JsonPropertyName("version")]
    public string Version { get; set; } = "0.1.0";
}

public class ServiceHealthResponse
{
    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("timestamp")]
    public string Timestamp { get; set; } = string.Empty;

    [JsonPropertyName("services")]
    public List<ServiceStatus> Services { get; set; } = [];

    [JsonPropertyName("database")]
    public ComponentHealth Database { get; set; } = new();

    [JsonPropertyName("redis")]
    public ComponentHealth Redis { get; set; } = new();
}

public class ServiceStatus
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("latency_ms")]
    public double LatencyMs { get; set; }

    [JsonPropertyName("message")]
    public string? Message { get; set; }
}

public class ComponentHealth
{
    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("latency_ms")]
    public double? LatencyMs { get; set; }

    [JsonPropertyName("message")]
    public string? Message { get; set; }
}
