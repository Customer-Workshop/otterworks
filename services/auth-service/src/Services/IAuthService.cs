using OtterWorks.AuthService.DTOs;

namespace OtterWorks.AuthService.Services;

public interface IAuthService
{
    Task<AuthResponse> RegisterAsync(RegisterRequest request);
    Task<AuthResponse> LoginAsync(LoginRequest request);
    Task<AuthResponse> RefreshTokenAsync(string token);
    Task ChangePasswordAsync(Guid userId, ChangePasswordRequest request);
    Task LogoutAsync(Guid userId);
}
