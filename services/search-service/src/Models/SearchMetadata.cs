using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.SearchService.Models;

[Table("search_metadata")]
public class SearchMetadata
{
    [Key]
    [Column("id")]
    public int Id { get; set; }

    [Required]
    [Column("key")]
    [MaxLength(256)]
    public string Key { get; set; } = string.Empty;

    [Required]
    [Column("value")]
    public string Value { get; set; } = string.Empty;

    [Column("updated_at")]
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
}
