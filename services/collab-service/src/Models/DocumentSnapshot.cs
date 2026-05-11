namespace OtterWorks.CollabService.Models;

public class DocumentSnapshot
{
    public string Id { get; set; } = string.Empty;

    public string DocumentId { get; set; } = string.Empty;

    public string State { get; set; } = string.Empty;

    public string CreatedAt { get; set; } = string.Empty;

    public string CreatedBy { get; set; } = string.Empty;

    public string? Label { get; set; }
}
