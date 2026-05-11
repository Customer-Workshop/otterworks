namespace OtterWorks.AnalyticsService.Services;

public interface IDataLakeExporter
{
    Task ExportAsync(string period);
}
