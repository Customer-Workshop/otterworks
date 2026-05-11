using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.DocumentService.Models;

[Table("templates")]
public class Template
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [Required]
    [MaxLength(500)]
    [Column("name")]
    public string Name { get; set; } = string.Empty;

    [Required]
    [Column("description")]
    public string Description { get; set; } = string.Empty;

    [Required]
    [Column("content")]
    public string Content { get; set; } = string.Empty;

    [Required]
    [MaxLength(50)]
    [Column("content_type")]
    public string ContentType { get; set; } = "text/markdown";

    [Column("created_by")]
    public Guid CreatedBy { get; set; }

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
}
