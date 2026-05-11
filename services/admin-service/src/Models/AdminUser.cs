using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.AdminService.Models;

[Table("admin_users")]
public class AdminUser
{
    public static readonly string[] ValidRoles = ["super_admin", "admin", "editor", "viewer"];
    public static readonly string[] ValidStatuses = ["active", "suspended", "deleted"];

    [Key]
    [Column("id")]
    public Guid Id { get; set; }

    [Required]
    [Column("email")]
    public string Email { get; set; } = string.Empty;

    [Required]
    [Column("display_name")]
    [MaxLength(255)]
    public string DisplayName { get; set; } = string.Empty;

    [Required]
    [Column("role")]
    public string Role { get; set; } = "viewer";

    [Required]
    [Column("status")]
    public string Status { get; set; } = "active";

    [Column("avatar_url")]
    public string? AvatarUrl { get; set; }

    [Column("metadata", TypeName = "jsonb")]
    public string Metadata { get; set; } = "{}";

    [Column("last_login_at")]
    public DateTime? LastLoginAt { get; set; }

    [Column("suspended_at")]
    public DateTime? SuspendedAt { get; set; }

    [Column("suspended_reason")]
    public string? SuspendedReason { get; set; }

    [Column("created_at")]
    public DateTime CreatedAt { get; set; }

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; }

    public StorageQuota? StorageQuota { get; set; }

    public void Suspend(string? reason = null)
    {
        Status = "suspended";
        SuspendedAt = DateTime.UtcNow;
        SuspendedReason = reason;
        UpdatedAt = DateTime.UtcNow;
    }

    public void Activate()
    {
        Status = "active";
        SuspendedAt = null;
        SuspendedReason = null;
        UpdatedAt = DateTime.UtcNow;
    }

    public void SoftDelete()
    {
        Status = "deleted";
        UpdatedAt = DateTime.UtcNow;
    }
}
