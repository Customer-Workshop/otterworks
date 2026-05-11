namespace OtterWorks.CollabService.Models;

public class CollaborationSession
{
    public Guid Id { get; set; }

    public string DocumentId { get; set; } = string.Empty;

    public string UserId { get; set; } = string.Empty;

    public string DisplayName { get; set; } = string.Empty;

    public DateTime JoinedAt { get; set; }

    public DateTime? LeftAt { get; set; }

    public bool IsActive { get; set; }
}
