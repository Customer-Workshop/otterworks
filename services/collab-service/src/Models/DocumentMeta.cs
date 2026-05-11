namespace OtterWorks.CollabService.Models;

public class DocumentMeta
{
    public string DocumentId { get; set; } = string.Empty;

    public string CreatedAt { get; set; } = string.Empty;

    public string LastModifiedAt { get; set; } = string.Empty;

    public string LastModifiedBy { get; set; } = string.Empty;

    public int Version { get; set; }
}
