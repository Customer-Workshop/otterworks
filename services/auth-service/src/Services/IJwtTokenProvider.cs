using OtterWorks.AuthService.Data.Entities;

namespace OtterWorks.AuthService.Services;

public interface IJwtTokenProvider
{
    string GenerateAccessToken(User user);
    string GenerateRefreshToken(User user);
    System.Security.Claims.ClaimsPrincipal ValidateAndGetClaims(string token);
    string ValidateTokenAndGetUserId(string token);
    string ValidateRefreshTokenAndGetUserId(string token);
    string ExtractJti(string token);
    bool IsTokenValid(string token);
    long AccessTokenExpiry { get; }
    long RefreshTokenExpiry { get; }
}
