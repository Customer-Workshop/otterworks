using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.DocumentService.Models;

[Table("document_versions")]
public class DocumentVersion
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [Column("document_id")]
    public Guid DocumentId { get; set; }

    [Column("version_number")]
    public int VersionNumber { get; set; }

    [Required]
    [MaxLength(500)]
    [Column("title")]
    public string Title { get; set; } = string.Empty;

    [Required]
    [Column("content")]
    public string Content { get; set; } = string.Empty;

    [Column("created_by")]
    public Guid CreatedBy { get; set; }

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [ForeignKey("DocumentId")]
    public Document? Document { get; set; }
}
