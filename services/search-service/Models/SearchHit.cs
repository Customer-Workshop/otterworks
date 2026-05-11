namespace OtterWorks.SearchService.Models;

public class SearchHit
{
    public string Id { get; set; } = string.Empty;
    public string Title { get; set; } = string.Empty;
    public string ContentSnippet { get; set; } = string.Empty;
    public string Type { get; set; } = string.Empty;
    public string OwnerId { get; set; } = string.Empty;
    public List<string> Tags { get; set; } = new();
    public double Score { get; set; }
    public Dictionary<string, List<string>> Highlights { get; set; } = new();
    public string? CreatedAt { get; set; }
    public string? UpdatedAt { get; set; }
    public string? MimeType { get; set; }
    public string? FolderId { get; set; }
    public int? Size { get; set; }

    public Dictionary<string, object?> ToDict()
    {
        var result = new Dictionary<string, object?>
        {
            ["id"] = Id,
            ["title"] = Title,
            ["content_snippet"] = ContentSnippet,
            ["type"] = Type,
            ["owner_id"] = OwnerId,
            ["tags"] = Tags,
            ["score"] = Score,
            ["highlights"] = Highlights,
        };

        if (CreatedAt is not null) result["created_at"] = CreatedAt;
        if (UpdatedAt is not null) result["updated_at"] = UpdatedAt;
        if (MimeType is not null) result["mime_type"] = MimeType;
        if (FolderId is not null) result["folder_id"] = FolderId;
        if (Size is not null) result["size"] = Size;

        return result;
    }
}
