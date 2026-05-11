using OtterWorks.AuthService.DTOs;

namespace OtterWorks.AuthService.Services;

public interface IUserService
{
    Task<UserDTO> GetProfileAsync(Guid userId);
    Task<UserDTO> UpdateProfileAsync(Guid userId, UpdateProfileRequest request);
    Task<PagedResult<UserDTO>> ListUsersAsync(int page, int size);
    Task<UserDTO> FindByEmailAsync(string email);
}

public sealed class PagedResult<T>
{
    public IReadOnlyList<T> Content { get; set; } = Array.Empty<T>();
    public int TotalElements { get; set; }
    public int TotalPages { get; set; }
    public int Size { get; set; }
    public int Number { get; set; }
}
