namespace OtterWorks.ReportService.Services;

public interface IReportDataFetcher
{
    Task<List<Dictionary<string, object>>> FetchAnalyticsDataAsync(DateTime dateFrom, DateTime dateTo, Dictionary<string, string>? parameters);
    Task<List<Dictionary<string, object>>> FetchAuditDataAsync(DateTime dateFrom, DateTime dateTo, Dictionary<string, string>? parameters);
    Task<List<Dictionary<string, object>>> FetchUserActivityDataAsync(DateTime dateFrom, DateTime dateTo, Dictionary<string, string>? parameters);
}
