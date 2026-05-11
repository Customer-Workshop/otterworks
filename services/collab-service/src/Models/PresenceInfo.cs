namespace OtterWorks.CollabService.Models;

public class PresenceInfo
{
    public string DocumentId { get; set; } = string.Empty;

    public List<UserAwareness> Users { get; set; } = [];

    public int Count { get; set; }
}
