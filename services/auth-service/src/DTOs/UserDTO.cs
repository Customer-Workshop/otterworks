using OtterWorks.AuthService.Data.Entities;

namespace OtterWorks.AuthService.DTOs;

public sealed class UserDTO
{
    public string Id { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string DisplayName { get; set; } = string.Empty;
    public string? AvatarUrl { get; set; }
    public ICollection<string> Roles { get; set; } = new List<string>();
    public bool EmailVerified { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
    public DateTime? LastLoginAt { get; set; }

    public static UserDTO FromEntity(User user)
    {
        return new UserDTO
        {
            Id = user.Id.ToString(),
            Email = user.Email,
            DisplayName = user.DisplayName,
            AvatarUrl = user.AvatarUrl,
            Roles = user.UserRoles.Select(ur => ur.Role).ToList(),
            EmailVerified = user.EmailVerified,
            CreatedAt = user.CreatedAt,
            UpdatedAt = user.UpdatedAt,
            LastLoginAt = user.LastLoginAt,
        };
    }
}
