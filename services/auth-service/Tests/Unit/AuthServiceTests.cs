using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.AuthService.Data;
using OtterWorks.AuthService.Data.Entities;
using OtterWorks.AuthService.DTOs;
using OtterWorks.AuthService.Services;

namespace AuthService.Tests.Unit;

public class AuthServiceTests : IDisposable
{
    private readonly AuthDbContext _db;
    private readonly Mock<IJwtTokenProvider> _mockJwtProvider;
    private readonly Mock<ILogger<OtterWorks.AuthService.Services.AuthService>> _mockLogger;
    private readonly OtterWorks.AuthService.Services.AuthService _authService;
    private readonly User _testUser;

    public AuthServiceTests()
    {
        var options = new DbContextOptionsBuilder<AuthDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;
        _db = new AuthDbContext(options);

        _mockJwtProvider = new Mock<IJwtTokenProvider>();
        _mockLogger = new Mock<ILogger<OtterWorks.AuthService.Services.AuthService>>();

        _authService = new OtterWorks.AuthService.Services.AuthService(_db, _mockJwtProvider.Object, _mockLogger.Object);

        _testUser = new User
        {
            Id = Guid.NewGuid(),
            Email = "test@otterworks.dev",
            DisplayName = "Test User",
            PasswordHash = BCrypt.Net.BCrypt.HashPassword("password123", workFactor: 12),
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
        };
    }

    [Fact]
    public async Task Register_ShouldCreateUserAndReturnTokens()
    {
        var request = new RegisterRequest
        {
            Email = "new@otterworks.dev",
            Password = "password123",
            DisplayName = "New User",
        };

        _mockJwtProvider.Setup(j => j.GenerateAccessToken(It.IsAny<User>())).Returns("access-token");
        _mockJwtProvider.Setup(j => j.GenerateRefreshToken(It.IsAny<User>())).Returns("refresh-token");
        _mockJwtProvider.Setup(j => j.ExtractJti("refresh-token")).Returns("jti-123");
        _mockJwtProvider.Setup(j => j.AccessTokenExpiry).Returns(3600);
        _mockJwtProvider.Setup(j => j.RefreshTokenExpiry).Returns(2592000);

        var response = await _authService.RegisterAsync(request);

        Assert.Equal("access-token", response.AccessToken);
        Assert.Equal("refresh-token", response.RefreshToken);
        Assert.Equal("Bearer", response.TokenType);
        Assert.True(await _db.Users.AnyAsync(u => u.Email == "new@otterworks.dev"));
    }

    [Fact]
    public async Task Register_ShouldThrowWhenEmailExists()
    {
        _db.Users.Add(_testUser);
        await _db.SaveChangesAsync();

        var request = new RegisterRequest
        {
            Email = "test@otterworks.dev",
            Password = "password123",
            DisplayName = "Existing User",
        };

        var ex = await Assert.ThrowsAsync<ArgumentException>(() => _authService.RegisterAsync(request));
        Assert.Equal("Email already registered", ex.Message);
    }

    [Fact]
    public async Task Login_ShouldReturnTokensForValidCredentials()
    {
        _testUser.UserRoles = new List<UserRole> { new() { UserId = _testUser.Id, Role = "USER" } };
        _db.Users.Add(_testUser);
        _db.UserRoles.Add(_testUser.UserRoles.First());
        await _db.SaveChangesAsync();

        _mockJwtProvider.Setup(j => j.GenerateAccessToken(It.IsAny<User>())).Returns("access-token");
        _mockJwtProvider.Setup(j => j.GenerateRefreshToken(It.IsAny<User>())).Returns("refresh-token");
        _mockJwtProvider.Setup(j => j.ExtractJti("refresh-token")).Returns("jti-456");
        _mockJwtProvider.Setup(j => j.AccessTokenExpiry).Returns(3600);
        _mockJwtProvider.Setup(j => j.RefreshTokenExpiry).Returns(2592000);

        var request = new LoginRequest
        {
            Email = "test@otterworks.dev",
            Password = "password123",
        };

        var response = await _authService.LoginAsync(request);

        Assert.Equal("access-token", response.AccessToken);
        Assert.Equal("test@otterworks.dev", response.User.Email);
    }

    [Fact]
    public async Task Login_ShouldThrowForInvalidEmail()
    {
        var request = new LoginRequest
        {
            Email = "nonexistent@otterworks.dev",
            Password = "password123",
        };

        var ex = await Assert.ThrowsAsync<ArgumentException>(() => _authService.LoginAsync(request));
        Assert.Equal("Invalid credentials", ex.Message);
    }

    [Fact]
    public async Task Login_ShouldThrowForWrongPassword()
    {
        _db.Users.Add(_testUser);
        await _db.SaveChangesAsync();

        var request = new LoginRequest
        {
            Email = "test@otterworks.dev",
            Password = "wrongpassword",
        };

        var ex = await Assert.ThrowsAsync<ArgumentException>(() => _authService.LoginAsync(request));
        Assert.Equal("Invalid credentials", ex.Message);
    }

    [Fact]
    public async Task ChangePassword_ShouldUpdatePasswordAndRevokeTokens()
    {
        _db.Users.Add(_testUser);
        _db.RefreshTokens.Add(new RefreshToken
        {
            Id = Guid.NewGuid(),
            UserId = _testUser.Id,
            TokenId = "old-jti",
            ExpiresAt = DateTime.UtcNow.AddDays(30),
            CreatedAt = DateTime.UtcNow,
        });
        await _db.SaveChangesAsync();

        var request = new ChangePasswordRequest
        {
            CurrentPassword = "password123",
            NewPassword = "newPassword123",
        };

        await _authService.ChangePasswordAsync(_testUser.Id, request);

        var updatedUser = await _db.Users.FindAsync(_testUser.Id);
        Assert.NotNull(updatedUser);
        Assert.True(BCrypt.Net.BCrypt.Verify("newPassword123", updatedUser.PasswordHash));
    }

    [Fact]
    public async Task ChangePassword_ShouldThrowForWrongCurrentPassword()
    {
        _db.Users.Add(_testUser);
        await _db.SaveChangesAsync();

        var request = new ChangePasswordRequest
        {
            CurrentPassword = "wrongPassword",
            NewPassword = "newPassword123",
        };

        var ex = await Assert.ThrowsAsync<ArgumentException>(
            () => _authService.ChangePasswordAsync(_testUser.Id, request));
        Assert.Equal("Current password is incorrect", ex.Message);
    }

    public void Dispose()
    {
        _db.Dispose();
        GC.SuppressFinalize(this);
    }
}
