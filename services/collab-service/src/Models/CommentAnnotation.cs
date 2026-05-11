namespace OtterWorks.CollabService.Models;

public class CommentAnnotation
{
    public string Id { get; set; } = string.Empty;

    public string DocumentId { get; set; } = string.Empty;

    public string ThreadId { get; set; } = string.Empty;

    public string Content { get; set; } = string.Empty;

    public CommentAuthor Author { get; set; } = new();

    public int RangeStart { get; set; }

    public int RangeEnd { get; set; }

    public string CreatedAt { get; set; } = string.Empty;

    public string? ParentId { get; set; }
}

public class CommentAuthor
{
    public string UserId { get; set; } = string.Empty;

    public string DisplayName { get; set; } = string.Empty;
}
