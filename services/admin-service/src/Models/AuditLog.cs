using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.AdminService.Models;

[Table("audit_logs")]
public class AuditLog
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; }

    [Column("actor_id")]
    public Guid? ActorId { get; set; }

    [Column("actor_email")]
    public string? ActorEmail { get; set; }

    [Required]
    [Column("action")]
    public string Action { get; set; } = string.Empty;

    [Required]
    [Column("resource_type")]
    public string ResourceType { get; set; } = string.Empty;

    [Column("resource_id")]
    public Guid? ResourceId { get; set; }

    [Column("changes_made", TypeName = "jsonb")]
    public string ChangesMade { get; set; } = "{}";

    [Column("ip_address")]
    public string? IpAddress { get; set; }

    [Column("user_agent")]
    public string? UserAgent { get; set; }

    [Column("created_at")]
    public DateTime CreatedAt { get; set; }

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; }
}
