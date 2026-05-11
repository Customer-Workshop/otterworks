using System.Text.Json.Serialization;

namespace OtterWorks.FileService.Models;

public class Folder
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; }

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("parent_id")]
    public Guid? ParentId { get; set; }

    [JsonPropertyName("owner_id")]
    public Guid OwnerId { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; set; }
}
