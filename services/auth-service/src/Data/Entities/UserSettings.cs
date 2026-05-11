using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.AuthService.Data.Entities;

[Table("user_settings")]
public class UserSettings
{
    [Key]
    [Column("user_id")]
    public Guid UserId { get; set; }

    [Column("notification_email")]
    public bool NotificationEmail { get; set; } = true;

    [Column("notification_in_app")]
    public bool NotificationInApp { get; set; } = true;

    [Column("notification_desktop")]
    public bool NotificationDesktop { get; set; }

    [Required]
    [MaxLength(10)]
    [Column("theme")]
    public string Theme { get; set; } = "system";

    [Required]
    [MaxLength(10)]
    [Column("language")]
    public string Language { get; set; } = "en";
}
