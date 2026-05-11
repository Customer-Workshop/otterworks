using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.AdminService.Models;

[Table("announcements")]
public class Announcement
{
    public static readonly string[] ValidSeverities = ["info", "warning", "critical", "maintenance"];
    public static readonly string[] ValidStatuses = ["draft", "published", "archived"];

    [Key]
    [Column("id")]
    public Guid Id { get; set; }

    [Required]
    [Column("title")]
    [MaxLength(255)]
    public string Title { get; set; } = string.Empty;

    [Required]
    [Column("body")]
    public string Body { get; set; } = string.Empty;

    [Required]
    [Column("severity")]
    public string Severity { get; set; } = "info";

    [Required]
    [Column("status")]
    public string Status { get; set; } = "draft";

    [Column("target_audience", TypeName = "jsonb")]
    public string TargetAudience { get; set; } = "{}";

    [Column("starts_at")]
    public DateTime? StartsAt { get; set; }

    [Column("ends_at")]
    public DateTime? EndsAt { get; set; }

    [Column("created_by")]
    public Guid? CreatedBy { get; set; }

    [Column("created_at")]
    public DateTime CreatedAt { get; set; }

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; }

    [NotMapped]
    public bool Active =>
        Status == "published" &&
        (!StartsAt.HasValue || StartsAt.Value <= DateTime.UtcNow) &&
        (!EndsAt.HasValue || EndsAt.Value >= DateTime.UtcNow);
}
