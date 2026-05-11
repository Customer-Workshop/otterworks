using System.Text.Json.Serialization;

namespace OtterWorks.FileService.Models;

public class FileVersion
{
    [JsonPropertyName("file_id")]
    public Guid FileId { get; set; }

    [JsonPropertyName("version")]
    public int Version { get; set; }

    [JsonPropertyName("s3_key")]
    public string S3Key { get; set; } = string.Empty;

    [JsonPropertyName("size_bytes")]
    public long SizeBytes { get; set; }

    [JsonPropertyName("created_by")]
    public Guid CreatedBy { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }
}
