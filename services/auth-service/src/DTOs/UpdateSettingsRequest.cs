namespace OtterWorks.AuthService.DTOs;

public sealed class UpdateSettingsRequest
{
    public bool? NotificationEmail { get; set; }
    public bool? NotificationInApp { get; set; }
    public bool? NotificationDesktop { get; set; }
    public string? Theme { get; set; }
    public string? Language { get; set; }
}
