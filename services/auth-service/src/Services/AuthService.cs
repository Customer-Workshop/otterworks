using Microsoft.EntityFrameworkCore;
using OtterWorks.AuthService.Data;
using OtterWorks.AuthService.Data.Entities;
using OtterWorks.AuthService.DTOs;

namespace OtterWorks.AuthService.Services;

public sealed class AuthService : IAuthService
{
    private readonly AuthDbContext _db;
    private readonly IJwtTokenProvider _jwtTokenProvider;
    private readonly ILogger<AuthService> _logger;

    public AuthService(AuthDbContext db, IJwtTokenProvider jwtTokenProvider, ILogger<AuthService> logger)
    {
        _db = db;
        _jwtTokenProvider = jwtTokenProvider;
        _logger = logger;
    }

    public async Task<AuthResponse> RegisterAsync(RegisterRequest request)
    {
        if (await _db.Users.AnyAsync(u => u.Email == request.Email))
        {
            throw new ArgumentException("Email already registered");
        }

        var user = new User
        {
            Id = Guid.NewGuid(),
            Email = request.Email,
            PasswordHash = BCrypt.Net.BCrypt.HashPassword(request.Password, workFactor: 12),
            DisplayName = request.DisplayName,
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
        };

        _db.Users.Add(user);

        var userRole = new UserRole { UserId = user.Id, Role = "USER" };
        _db.UserRoles.Add(userRole);

        await _db.SaveChangesAsync();

        user.UserRoles = new List<UserRole> { userRole };

        _logger.LogInformation("User registered: email={Email}", user.Email);
        return BuildAuthResponse(user);
    }

    public async Task<AuthResponse> LoginAsync(LoginRequest request)
    {
        var user = await _db.Users
            .Include(u => u.UserRoles)
            .FirstOrDefaultAsync(u => u.Email == request.Email)
            ?? throw new ArgumentException("Invalid credentials");

        if (!BCrypt.Net.BCrypt.Verify(request.Password, user.PasswordHash))
        {
            throw new ArgumentException("Invalid credentials");
        }

        user.LastLoginAt = DateTime.UtcNow;
        await _db.SaveChangesAsync();

        _logger.LogInformation("User logged in: email={Email}", user.Email);
        return BuildAuthResponse(user);
    }

    public async Task<AuthResponse> RefreshTokenAsync(string token)
    {
        var jti = _jwtTokenProvider.ExtractJti(token);
        var userId = _jwtTokenProvider.ValidateRefreshTokenAndGetUserId(token);

        var storedToken = await _db.RefreshTokens
            .FirstOrDefaultAsync(rt => rt.TokenId == jti && !rt.Revoked)
            ?? throw new ArgumentException("Invalid or revoked refresh token");

        if (storedToken.ExpiresAt < DateTime.UtcNow)
        {
            throw new ArgumentException("Refresh token expired");
        }

        storedToken.Revoked = true;
        await _db.SaveChangesAsync();

        var user = await _db.Users
            .Include(u => u.UserRoles)
            .FirstOrDefaultAsync(u => u.Id == Guid.Parse(userId))
            ?? throw new ArgumentException("User not found");

        _logger.LogInformation("Token refreshed for user: {Email}", user.Email);
        return BuildAuthResponse(user);
    }

    public async Task ChangePasswordAsync(Guid userId, ChangePasswordRequest request)
    {
        var user = await _db.Users.FindAsync(userId)
            ?? throw new ArgumentException("User not found");

        if (!BCrypt.Net.BCrypt.Verify(request.CurrentPassword, user.PasswordHash))
        {
            throw new ArgumentException("Current password is incorrect");
        }

        user.PasswordHash = BCrypt.Net.BCrypt.HashPassword(request.NewPassword, workFactor: 12);
        user.UpdatedAt = DateTime.UtcNow;

        var tokens = await _db.RefreshTokens.Where(rt => rt.UserId == userId).ToListAsync();
        foreach (var t in tokens)
        {
            t.Revoked = true;
        }

        await _db.SaveChangesAsync();

        _logger.LogInformation("Password changed for user: {UserId}", userId);
    }

    public async Task LogoutAsync(Guid userId)
    {
        var tokens = await _db.RefreshTokens.Where(rt => rt.UserId == userId).ToListAsync();
        foreach (var t in tokens)
        {
            t.Revoked = true;
        }

        await _db.SaveChangesAsync();

        _logger.LogInformation("User logged out: {UserId}", userId);
    }

    private AuthResponse BuildAuthResponse(User user)
    {
        var accessToken = _jwtTokenProvider.GenerateAccessToken(user);
        var refreshTokenStr = _jwtTokenProvider.GenerateRefreshToken(user);

        var jti = _jwtTokenProvider.ExtractJti(refreshTokenStr);
        var refreshToken = new Data.Entities.RefreshToken
        {
            Id = Guid.NewGuid(),
            UserId = user.Id,
            TokenId = jti,
            ExpiresAt = DateTime.UtcNow.AddSeconds(_jwtTokenProvider.RefreshTokenExpiry),
            CreatedAt = DateTime.UtcNow,
        };
        _db.RefreshTokens.Add(refreshToken);
        _db.SaveChanges();

        return new AuthResponse
        {
            AccessToken = accessToken,
            RefreshToken = refreshTokenStr,
            TokenType = "Bearer",
            ExpiresIn = _jwtTokenProvider.AccessTokenExpiry,
            User = new AuthUserDto
            {
                Id = user.Id.ToString(),
                Email = user.Email,
                DisplayName = user.DisplayName,
                AvatarUrl = user.AvatarUrl,
            },
        };
    }
}
