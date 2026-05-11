using OtterWorks.AuthService.Data.Entities;

namespace OtterWorks.AuthService.DTOs;

public sealed class UserSettingsDTO
{
    public bool NotificationEmail { get; set; }
    public bool NotificationInApp { get; set; }
    public bool NotificationDesktop { get; set; }
    public string Theme { get; set; } = string.Empty;
    public string Language { get; set; } = string.Empty;

    public static UserSettingsDTO FromEntity(UserSettings entity)
    {
        return new UserSettingsDTO
        {
            NotificationEmail = entity.NotificationEmail,
            NotificationInApp = entity.NotificationInApp,
            NotificationDesktop = entity.NotificationDesktop,
            Theme = entity.Theme,
            Language = entity.Language,
        };
    }
}
