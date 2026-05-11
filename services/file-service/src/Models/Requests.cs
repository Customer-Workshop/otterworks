using System.Text.Json.Serialization;

namespace OtterWorks.FileService.Models;

public class MoveFileRequest
{
    [JsonPropertyName("folder_id")]
    public Guid? FolderId { get; set; }
}

public class RenameFileRequest
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;
}

public class ShareFileRequest
{
    [JsonPropertyName("shared_with")]
    public Guid SharedWith { get; set; }

    [JsonPropertyName("permission")]
    [JsonConverter(typeof(JsonStringEnumConverter<SharePermission>))]
    public SharePermission Permission { get; set; }

    [JsonPropertyName("shared_by")]
    public Guid SharedBy { get; set; }
}

public class CreateFolderRequest
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("parent_id")]
    public Guid? ParentId { get; set; }

    [JsonPropertyName("owner_id")]
    public Guid OwnerId { get; set; }
}

public class UpdateFolderRequest
{
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    [JsonPropertyName("parent_id")]
    public Guid? ParentId { get; set; }
}
