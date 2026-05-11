using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.DocumentService.Models;

[Table("documents")]
public class Document
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [Required]
    [MaxLength(500)]
    [Column("title")]
    public string Title { get; set; } = string.Empty;

    [Required]
    [Column("content")]
    public string Content { get; set; } = string.Empty;

    [Required]
    [MaxLength(50)]
    [Column("content_type")]
    public string ContentType { get; set; } = "text/markdown";

    [Column("owner_id")]
    public Guid OwnerId { get; set; }

    [Column("folder_id")]
    public Guid? FolderId { get; set; }

    [Column("is_deleted")]
    public bool IsDeleted { get; set; }

    [Column("is_template")]
    public bool IsTemplate { get; set; }

    [Column("word_count")]
    public int WordCount { get; set; }

    [Column("version")]
    public int Version { get; set; } = 1;

    [Column("created_at")]
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;

    public List<DocumentVersion> Versions { get; set; } = [];

    public List<Comment> Comments { get; set; } = [];
}
