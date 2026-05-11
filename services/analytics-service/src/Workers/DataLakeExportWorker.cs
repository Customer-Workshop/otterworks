using OtterWorks.AnalyticsService.Services;

namespace OtterWorks.AnalyticsService.Workers;

public class DataLakeExportWorker : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<DataLakeExportWorker> _logger;

    public DataLakeExportWorker(IServiceScopeFactory scopeFactory, ILogger<DataLakeExportWorker> logger)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("Data lake export worker started");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await Task.Delay(TimeSpan.FromHours(1), stoppingToken);

                using var scope = _scopeFactory.CreateScope();
                var exporter = scope.ServiceProvider.GetRequiredService<IDataLakeExporter>();
                await exporter.ExportAsync("daily");

                _logger.LogInformation("Data lake export completed");
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Data lake export failed");
            }
        }

        _logger.LogInformation("Data lake export worker stopped");
    }
}
