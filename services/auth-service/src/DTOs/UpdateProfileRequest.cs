namespace OtterWorks.AuthService.DTOs;

public sealed class UpdateProfileRequest
{
    public string? DisplayName { get; set; }
    public string? AvatarUrl { get; set; }
}
