using Microsoft.EntityFrameworkCore;
using OtterWorks.AuthService.Data;
using OtterWorks.AuthService.Data.Entities;
using OtterWorks.AuthService.DTOs;

namespace OtterWorks.AuthService.Services;

public sealed class UserSettingsService : IUserSettingsService
{
    private readonly AuthDbContext _db;
    private readonly ILogger<UserSettingsService> _logger;

    public UserSettingsService(AuthDbContext db, ILogger<UserSettingsService> logger)
    {
        _db = db;
        _logger = logger;
    }

    public async Task<UserSettingsDTO> GetSettingsAsync(Guid userId)
    {
        var settings = await _db.UserSettings.FindAsync(userId);
        if (settings == null)
        {
            settings = await CreateDefaultSettingsAsync(userId);
        }

        return UserSettingsDTO.FromEntity(settings);
    }

    public async Task<UserSettingsDTO> UpdateSettingsAsync(Guid userId, UpdateSettingsRequest request)
    {
        var settings = await _db.UserSettings.FindAsync(userId);
        if (settings == null)
        {
            settings = await CreateDefaultSettingsAsync(userId);
        }

        if (request.NotificationEmail.HasValue)
        {
            settings.NotificationEmail = request.NotificationEmail.Value;
        }

        if (request.NotificationInApp.HasValue)
        {
            settings.NotificationInApp = request.NotificationInApp.Value;
        }

        if (request.NotificationDesktop.HasValue)
        {
            settings.NotificationDesktop = request.NotificationDesktop.Value;
        }

        if (request.Theme != null)
        {
            settings.Theme = request.Theme;
        }

        if (request.Language != null)
        {
            settings.Language = request.Language;
        }

        await _db.SaveChangesAsync();
        _logger.LogInformation("Settings updated for user: {UserId}", userId);
        return UserSettingsDTO.FromEntity(settings);
    }

    private async Task<UserSettings> CreateDefaultSettingsAsync(Guid userId)
    {
        var userExists = await _db.Users.AnyAsync(u => u.Id == userId);
        if (!userExists)
        {
            throw new ArgumentException("User not found");
        }

        var settings = new UserSettings { UserId = userId };
        _db.UserSettings.Add(settings);
        await _db.SaveChangesAsync();
        return settings;
    }
}
