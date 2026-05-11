using System.Text.Json.Serialization;

namespace OtterWorks.FileService.Models;

public class FileShare
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; }

    [JsonPropertyName("file_id")]
    public Guid FileId { get; set; }

    [JsonPropertyName("shared_with")]
    public Guid SharedWith { get; set; }

    [JsonPropertyName("permission")]
    [JsonConverter(typeof(JsonStringEnumConverter))]
    public SharePermission Permission { get; set; }

    [JsonPropertyName("shared_by")]
    public Guid SharedBy { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum SharePermission
{
    Viewer,
    Editor,
}
