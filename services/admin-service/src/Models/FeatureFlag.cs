using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.AdminService.Models;

[Table("feature_flags")]
public class FeatureFlag
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; }

    [Required]
    [Column("name")]
    public string Name { get; set; } = string.Empty;

    [Column("description")]
    public string? Description { get; set; }

    [Required]
    [Column("enabled")]
    public bool Enabled { get; set; }

    [Column("target_users", TypeName = "jsonb")]
    public string TargetUsers { get; set; } = "[]";

    [Column("target_groups", TypeName = "jsonb")]
    public string TargetGroups { get; set; } = "[]";

    [Column("rollout_percentage")]
    public int RolloutPercentage { get; set; }

    [Column("expires_at")]
    public DateTime? ExpiresAt { get; set; }

    [Column("created_at")]
    public DateTime CreatedAt { get; set; }

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; }

    [NotMapped]
    public bool Expired => ExpiresAt.HasValue && ExpiresAt.Value < DateTime.UtcNow;
}
