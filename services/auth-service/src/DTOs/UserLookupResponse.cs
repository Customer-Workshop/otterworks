namespace OtterWorks.AuthService.DTOs;

public sealed class UserLookupResponse
{
    public string Id { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public string DisplayName { get; set; } = string.Empty;

    public static UserLookupResponse FromUserDTO(UserDTO dto)
    {
        return new UserLookupResponse
        {
            Id = dto.Id,
            Email = dto.Email,
            DisplayName = dto.DisplayName,
        };
    }
}
