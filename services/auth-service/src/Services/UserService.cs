using Microsoft.EntityFrameworkCore;
using OtterWorks.AuthService.Data;
using OtterWorks.AuthService.DTOs;

namespace OtterWorks.AuthService.Services;

public sealed class UserService : IUserService
{
    private readonly AuthDbContext _db;
    private readonly ILogger<UserService> _logger;

    public UserService(AuthDbContext db, ILogger<UserService> logger)
    {
        _db = db;
        _logger = logger;
    }

    public async Task<UserDTO> GetProfileAsync(Guid userId)
    {
        var user = await _db.Users
            .Include(u => u.UserRoles)
            .FirstOrDefaultAsync(u => u.Id == userId)
            ?? throw new ArgumentException("User not found");

        return UserDTO.FromEntity(user);
    }

    public async Task<UserDTO> UpdateProfileAsync(Guid userId, UpdateProfileRequest request)
    {
        var user = await _db.Users
            .Include(u => u.UserRoles)
            .FirstOrDefaultAsync(u => u.Id == userId)
            ?? throw new ArgumentException("User not found");

        if (request.DisplayName != null)
        {
            user.DisplayName = request.DisplayName;
        }

        if (request.AvatarUrl != null)
        {
            user.AvatarUrl = request.AvatarUrl;
        }

        user.UpdatedAt = DateTime.UtcNow;
        await _db.SaveChangesAsync();

        _logger.LogInformation("Profile updated for user: {UserId}", userId);
        return UserDTO.FromEntity(user);
    }

    public async Task<PagedResult<UserDTO>> ListUsersAsync(int page, int size)
    {
        var totalElements = await _db.Users.CountAsync();
        var users = await _db.Users
            .Include(u => u.UserRoles)
            .OrderBy(u => u.CreatedAt)
            .Skip(page * size)
            .Take(size)
            .ToListAsync();

        return new PagedResult<UserDTO>
        {
            Content = users.Select(UserDTO.FromEntity).ToList(),
            TotalElements = totalElements,
            TotalPages = (int)Math.Ceiling((double)totalElements / size),
            Size = size,
            Number = page,
        };
    }

    public async Task<UserDTO> FindByEmailAsync(string email)
    {
        var user = await _db.Users
            .Include(u => u.UserRoles)
            .FirstOrDefaultAsync(u => u.Email == email)
            ?? throw new ArgumentException($"User not found with email: {email}");

        return UserDTO.FromEntity(user);
    }
}
