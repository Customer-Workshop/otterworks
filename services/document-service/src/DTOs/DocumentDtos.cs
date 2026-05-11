using System.Text.Json.Serialization;

namespace OtterWorks.DocumentService.DTOs;

public class DocumentCreateRequest
{
    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;

    [JsonPropertyName("content_type")]
    public string ContentType { get; set; } = "text/markdown";

    [JsonPropertyName("owner_id")]
    public Guid? OwnerId { get; set; }

    [JsonPropertyName("folder_id")]
    public Guid? FolderId { get; set; }
}

public class DocumentUpdateRequest
{
    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;

    [JsonPropertyName("content_type")]
    public string ContentType { get; set; } = "text/markdown";

    [JsonPropertyName("folder_id")]
    public Guid? FolderId { get; set; }
}

public class DocumentPatchRequest
{
    [JsonPropertyName("title")]
    public string? Title { get; set; }

    [JsonPropertyName("content")]
    public string? Content { get; set; }

    [JsonPropertyName("content_type")]
    public string? ContentType { get; set; }

    [JsonPropertyName("folder_id")]
    public Guid? FolderId { get; set; }

    public HashSet<string> ProvidedFields { get; set; } = [];
}

public class DocumentResponse
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; }

    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;

    [JsonPropertyName("content_type")]
    public string ContentType { get; set; } = string.Empty;

    [JsonPropertyName("owner_id")]
    public Guid OwnerId { get; set; }

    [JsonPropertyName("folder_id")]
    public Guid? FolderId { get; set; }

    [JsonPropertyName("is_deleted")]
    public bool IsDeleted { get; set; }

    [JsonPropertyName("is_template")]
    public bool IsTemplate { get; set; }

    [JsonPropertyName("word_count")]
    public int WordCount { get; set; }

    [JsonPropertyName("version")]
    public int Version { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; set; }
}

public class DocumentListResponse
{
    [JsonPropertyName("items")]
    public List<DocumentResponse> Items { get; set; } = [];

    [JsonPropertyName("total")]
    public int Total { get; set; }

    [JsonPropertyName("page")]
    public int Page { get; set; }

    [JsonPropertyName("size")]
    public int Size { get; set; }

    [JsonPropertyName("pages")]
    public int Pages { get; set; }
}

public class DocumentVersionResponse
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; }

    [JsonPropertyName("document_id")]
    public Guid DocumentId { get; set; }

    [JsonPropertyName("version_number")]
    public int VersionNumber { get; set; }

    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;

    [JsonPropertyName("created_by")]
    public Guid CreatedBy { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }
}

public class CommentCreateRequest
{
    [JsonPropertyName("author_id")]
    public Guid AuthorId { get; set; }

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;
}

public class CommentResponse
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; }

    [JsonPropertyName("document_id")]
    public Guid DocumentId { get; set; }

    [JsonPropertyName("author_id")]
    public Guid AuthorId { get; set; }

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; set; }
}

public class TemplateCreateRequest
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;

    [JsonPropertyName("content_type")]
    public string ContentType { get; set; } = "text/markdown";

    [JsonPropertyName("created_by")]
    public Guid CreatedBy { get; set; }
}

public class TemplateResponse
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; }

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;

    [JsonPropertyName("content_type")]
    public string ContentType { get; set; } = string.Empty;

    [JsonPropertyName("created_by")]
    public Guid CreatedBy { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }

    [JsonPropertyName("updated_at")]
    public DateTime UpdatedAt { get; set; }
}

public class DocumentFromTemplateRequest
{
    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("owner_id")]
    public Guid OwnerId { get; set; }

    [JsonPropertyName("folder_id")]
    public Guid? FolderId { get; set; }
}
