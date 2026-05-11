using OtterWorks.AuthService.DTOs;

namespace OtterWorks.AuthService.Services;

public interface IUserSettingsService
{
    Task<UserSettingsDTO> GetSettingsAsync(Guid userId);
    Task<UserSettingsDTO> UpdateSettingsAsync(Guid userId, UpdateSettingsRequest request);
}
