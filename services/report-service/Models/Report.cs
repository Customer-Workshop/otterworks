using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace OtterWorks.ReportService.Models;

[Table("reports")]
public class Report
{
    [Key]
    [DatabaseGenerated(DatabaseGeneratedOption.Identity)]
    [Column("id")]
    public long Id { get; set; }

    [Required]
    [Column("report_name")]
    public string ReportName { get; set; } = string.Empty;

    [Required]
    [Column("category")]
    public ReportCategory Category { get; set; }

    [Required]
    [Column("report_type")]
    public ReportType ReportType { get; set; }

    [Required]
    [Column("status")]
    public ReportStatus Status { get; set; }

    [Column("requested_by")]
    public string RequestedBy { get; set; } = string.Empty;

    [Column("date_from")]
    public DateTime? DateFrom { get; set; }

    [Column("date_to")]
    public DateTime? DateTo { get; set; }

    [Required]
    [Column("created_at")]
    public DateTime CreatedAt { get; set; }

    [Column("completed_at")]
    public DateTime? CompletedAt { get; set; }

    [Column("file_path")]
    public string? FilePath { get; set; }

    [Column("file_size_bytes")]
    public long? FileSizeBytes { get; set; }

    [Column("row_count")]
    public int? RowCount { get; set; }

    [Column("error_message")]
    public string? ErrorMessage { get; set; }

    [Column("parameters")]
    public string? Parameters { get; set; }
}
