using System.Text.Json.Serialization;

namespace OtterWorks.FileService.Models;

public class HealthResponse
{
    [JsonPropertyName("status")]
    public string Status { get; set; } = "healthy";

    [JsonPropertyName("service")]
    public string Service { get; set; } = "file-service";

    [JsonPropertyName("version")]
    public string Version { get; set; } = "0.1.0";
}

public class UploadResponse
{
    [JsonPropertyName("file")]
    public FileMetadata File { get; set; } = null!;
}

public class DownloadResponse
{
    [JsonPropertyName("url")]
    public string Url { get; set; } = string.Empty;

    [JsonPropertyName("expires_in_secs")]
    public long ExpiresInSecs { get; set; }
}

public class ListFilesResponse
{
    [JsonPropertyName("files")]
    public List<FileMetadata> Files { get; set; } = new();

    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("page")]
    public int Page { get; set; }

    [JsonPropertyName("page_size")]
    public int PageSize { get; set; }
}

public class ListVersionsResponse
{
    [JsonPropertyName("versions")]
    public List<FileVersion> Versions { get; set; } = new();
}

public class ListFoldersResponse
{
    [JsonPropertyName("folders")]
    public List<Folder> Folders { get; set; } = new();
}

public class ShareFileResponse
{
    [JsonPropertyName("share")]
    public FileShare Share { get; set; } = null!;
}

public class ErrorResponse
{
    [JsonPropertyName("error")]
    public string Error { get; set; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; set; } = string.Empty;
}

public class FileDetailResponse : FileMetadata
{
    [JsonPropertyName("shared_with")]
    public List<FileShare> SharedWith { get; set; } = new();
}

public class ActivityItem
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("type")]
    public string Type { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("actor_name")]
    public string ActorName { get; set; } = string.Empty;

    [JsonPropertyName("resource_name")]
    public string ResourceName { get; set; } = string.Empty;

    [JsonPropertyName("resource_type")]
    public string ResourceType { get; set; } = string.Empty;

    [JsonPropertyName("resource_id")]
    public string ResourceId { get; set; } = string.Empty;

    [JsonPropertyName("created_at")]
    public string CreatedAt { get; set; } = string.Empty;
}

public class ActivityResponse
{
    [JsonPropertyName("items")]
    public List<ActivityItem> Items { get; set; } = new();
}
