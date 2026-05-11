using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using Microsoft.Extensions.Options;
using OtterWorks.AuthService.Config;
using OtterWorks.AuthService.Data.Entities;
using OtterWorks.AuthService.Services;

namespace AuthService.Tests.Unit;

public class JwtTokenProviderTests
{
    private readonly JwtTokenProvider _jwtTokenProvider;

    public JwtTokenProviderTests()
    {
        var settings = Options.Create(new JwtSettings
        {
            Secret = "test-jwt-secret-otterworks-must-be-at-least-32-bytes-long-for-hmac",
            AccessTokenExpirySeconds = 3600,
            RefreshTokenExpirySeconds = 2592000,
        });
        _jwtTokenProvider = new JwtTokenProvider(settings);
    }

    [Fact]
    public void GenerateAccessToken_ShouldContainUserClaims()
    {
        var user = CreateTestUser();

        var token = _jwtTokenProvider.GenerateAccessToken(user);

        Assert.NotEmpty(token);
        var principal = _jwtTokenProvider.ValidateAndGetClaims(token);

        var subject = principal.FindFirst(JwtRegisteredClaimNames.Sub)?.Value
            ?? principal.FindFirst(ClaimTypes.NameIdentifier)?.Value;
        Assert.Equal(user.Id.ToString(), subject);

        var email = principal.FindFirst("email")?.Value;
        Assert.Equal("test@otterworks.dev", email);

        var name = principal.FindFirst("name")?.Value;
        Assert.Equal("Test User", name);

        var type = principal.FindFirst("type")?.Value;
        Assert.Equal("access", type);

        var roles = principal.FindAll("roles").Select(c => c.Value).ToList();
        Assert.Contains("USER", roles);
    }

    [Fact]
    public void GenerateRefreshToken_ShouldContainJtiAndType()
    {
        var user = CreateTestUser();

        var token = _jwtTokenProvider.GenerateRefreshToken(user);

        Assert.NotEmpty(token);
        var principal = _jwtTokenProvider.ValidateAndGetClaims(token);

        var subject = principal.FindFirst(JwtRegisteredClaimNames.Sub)?.Value
            ?? principal.FindFirst(ClaimTypes.NameIdentifier)?.Value;
        Assert.Equal(user.Id.ToString(), subject);

        var type = principal.FindFirst("type")?.Value;
        Assert.Equal("refresh", type);

        var jti = principal.FindFirst(JwtRegisteredClaimNames.Jti)?.Value;
        Assert.NotNull(jti);
        Assert.NotEmpty(jti);
    }

    [Fact]
    public void ValidateTokenAndGetUserId_ShouldReturnUserId()
    {
        var user = CreateTestUser();
        var token = _jwtTokenProvider.GenerateAccessToken(user);

        var userId = _jwtTokenProvider.ValidateTokenAndGetUserId(token);

        Assert.Equal(user.Id.ToString(), userId);
    }

    [Fact]
    public void ExtractJti_ShouldReturnJtiFromRefreshToken()
    {
        var user = CreateTestUser();
        var token = _jwtTokenProvider.GenerateRefreshToken(user);

        var jti = _jwtTokenProvider.ExtractJti(token);

        Assert.NotNull(jti);
        Assert.NotEmpty(jti);
    }

    [Fact]
    public void IsTokenValid_ShouldReturnTrueForValidToken()
    {
        var user = CreateTestUser();
        var token = _jwtTokenProvider.GenerateAccessToken(user);

        Assert.True(_jwtTokenProvider.IsTokenValid(token));
    }

    [Fact]
    public void IsTokenValid_ShouldReturnFalseForInvalidToken()
    {
        Assert.False(_jwtTokenProvider.IsTokenValid("invalid.token.here"));
    }

    [Fact]
    public void IsTokenValid_ShouldReturnFalseForExpiredToken()
    {
        var settings = Options.Create(new JwtSettings
        {
            Secret = "test-jwt-secret-otterworks-must-be-at-least-32-bytes-long-for-hmac",
            AccessTokenExpirySeconds = 1,
            RefreshTokenExpirySeconds = 1,
        });
        var shortLivedProvider = new JwtTokenProvider(settings);
        var user = CreateTestUser();
        var token = shortLivedProvider.GenerateAccessToken(user);

        Thread.Sleep(1500);

        Assert.False(shortLivedProvider.IsTokenValid(token));
    }

    [Fact]
    public void GetAccessTokenExpiry_ShouldReturnConfiguredValue()
    {
        Assert.Equal(3600, _jwtTokenProvider.AccessTokenExpiry);
    }

    [Fact]
    public void GetRefreshTokenExpiry_ShouldReturnConfiguredValue()
    {
        Assert.Equal(2592000, _jwtTokenProvider.RefreshTokenExpiry);
    }

    private static User CreateTestUser()
    {
        var user = new User
        {
            Id = Guid.NewGuid(),
            Email = "test@otterworks.dev",
            DisplayName = "Test User",
            PasswordHash = "$2a$12$hashedpassword",
        };
        user.UserRoles = new List<UserRole>
        {
            new() { UserId = user.Id, Role = "USER" },
        };
        return user;
    }
}
