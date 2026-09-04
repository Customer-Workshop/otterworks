namespace OtterWorks.AuditService.Security;

public class AuthorizationSettings
{
    /// <summary>User ids allowed to read and administer every user's audit data.</summary>
    public List<string> AdminUserIds { get; set; } = new();

    /// <summary>Internal service principals allowed to record events on behalf of other users.</summary>
    public List<string> ServiceAccountIds { get; set; } = new();
}
