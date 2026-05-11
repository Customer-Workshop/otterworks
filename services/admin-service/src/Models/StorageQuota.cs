using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.AdminService.Models;

[Table("storage_quotas")]
public class StorageQuota
{
    public static readonly string[] ValidTiers = ["free", "basic", "pro", "enterprise"];

    [Key]
    [Column("id")]
    public Guid Id { get; set; }

    [Required]
    [Column("user_id")]
    public Guid UserId { get; set; }

    [Required]
    [Column("quota_bytes")]
    public long QuotaBytes { get; set; } = 5368709120;

    [Required]
    [Column("used_bytes")]
    public long UsedBytes { get; set; }

    [Required]
    [Column("tier")]
    public string Tier { get; set; } = "free";

    [Column("created_at")]
    public DateTime CreatedAt { get; set; }

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; }

    [NotMapped]
    public double UsagePercentage => QuotaBytes == 0 ? 0 : Math.Round((double)UsedBytes / QuotaBytes * 100, 2);

    [NotMapped]
    public bool OverQuota => UsedBytes >= QuotaBytes;

    [NotMapped]
    public long RemainingBytes => Math.Max(QuotaBytes - UsedBytes, 0);
}
