namespace OtterWorks.CollabService.Models;

public class AuthenticatedUser
{
    public string UserId { get; set; } = string.Empty;

    public string Email { get; set; } = string.Empty;

    public string DisplayName { get; set; } = string.Empty;

    public string[] Roles { get; set; } = [];
}
