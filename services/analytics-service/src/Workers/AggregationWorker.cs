using System.Threading.Channels;
using OtterWorks.AnalyticsService.Models;

namespace OtterWorks.AnalyticsService.Workers;

public class AggregationWorker : BackgroundService
{
    private readonly Channel<AnalyticsEvent> _channel;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<AggregationWorker> _logger;

    public AggregationWorker(
        Channel<AnalyticsEvent> channel,
        IServiceScopeFactory scopeFactory,
        ILogger<AggregationWorker> logger)
    {
        _channel = channel;
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("Aggregation worker started");

        await foreach (var analyticsEvent in _channel.Reader.ReadAllAsync(stoppingToken))
        {
            try
            {
                using var scope = _scopeFactory.CreateScope();
                var repository = scope.ServiceProvider.GetRequiredService<Services.IMetricsRepository>();
                await repository.StoreEventAsync(analyticsEvent);
                _logger.LogDebug("Aggregation worker processed event {EventId}", analyticsEvent.EventId);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Aggregation worker failed to process event {EventId}", analyticsEvent.EventId);
            }
        }

        _logger.LogInformation("Aggregation worker stopped");
    }
}
