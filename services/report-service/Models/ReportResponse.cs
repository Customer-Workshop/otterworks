namespace OtterWorks.ReportService.Models;

public record ReportResponse(
    long Id,
    string ReportName,
    string Category,
    string ReportType,
    string Status,
    string RequestedBy,
    DateTime? DateFrom,
    DateTime? DateTo,
    DateTime CreatedAt,
    DateTime? CompletedAt,
    long? FileSizeBytes,
    int? RowCount,
    string? DownloadUrl,
    string? ErrorMessage)
{
    public static ReportResponse FromEntity(Report report)
    {
        return new ReportResponse(
            Id: report.Id,
            ReportName: report.ReportName,
            Category: report.Category.ToString(),
            ReportType: report.ReportType.ToString(),
            Status: report.Status.ToString(),
            RequestedBy: report.RequestedBy,
            DateFrom: report.DateFrom,
            DateTo: report.DateTo,
            CreatedAt: report.CreatedAt,
            CompletedAt: report.CompletedAt,
            FileSizeBytes: report.FileSizeBytes,
            RowCount: report.RowCount,
            DownloadUrl: report.FilePath != null ? $"/api/v1/reports/{report.Id}/download" : null,
            ErrorMessage: report.ErrorMessage);
    }
}
