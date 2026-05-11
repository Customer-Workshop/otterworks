namespace OtterWorks.ReportService.Models;

public class ReportResponse
{
    public long Id { get; set; }

    public string? ReportName { get; set; }

    public string? Category { get; set; }

    public string? ReportType { get; set; }

    public string? Status { get; set; }

    public string? RequestedBy { get; set; }

    public DateTime? DateFrom { get; set; }

    public DateTime? DateTo { get; set; }

    public DateTime? CreatedAt { get; set; }

    public DateTime? CompletedAt { get; set; }

    public long? FileSizeBytes { get; set; }

    public int? RowCount { get; set; }

    public string? DownloadUrl { get; set; }

    public string? ErrorMessage { get; set; }

    public static ReportResponse FromEntity(Report report)
    {
        var response = new ReportResponse
        {
            Id = report.Id,
            ReportName = report.ReportName,
            Category = report.Category.ToString(),
            ReportType = report.ReportType.ToString(),
            Status = report.Status.ToString(),
            RequestedBy = report.RequestedBy,
            DateFrom = report.DateFrom,
            DateTo = report.DateTo,
            CreatedAt = report.CreatedAt,
            CompletedAt = report.CompletedAt,
            FileSizeBytes = report.FileSizeBytes,
            RowCount = report.RowCount,
            ErrorMessage = report.ErrorMessage,
        };

        if (report.FilePath != null)
        {
            response.DownloadUrl = $"/api/v1/reports/{report.Id}/download";
        }

        return response;
    }
}
