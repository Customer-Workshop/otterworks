using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.AdminService.Models;

[Table("system_configs")]
public class SystemConfig
{
    public static readonly string[] ValidValueTypes = ["string", "integer", "boolean", "json"];

    [Key]
    [Column("id")]
    public Guid Id { get; set; }

    [Required]
    [Column("key")]
    public string Key { get; set; } = string.Empty;

    [Required]
    [Column("value")]
    public string Value { get; set; } = string.Empty;

    [Required]
    [Column("value_type")]
    public string ValueType { get; set; } = "string";

    [Column("description")]
    public string? Description { get; set; }

    [Required]
    [Column("is_secret")]
    public bool IsSecret { get; set; }

    [Column("created_at")]
    public DateTime CreatedAt { get; set; }

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; }
}
