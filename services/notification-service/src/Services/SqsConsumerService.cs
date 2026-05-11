using System.Text.Json;
using System.Threading.Channels;
using Amazon.SQS;
using Amazon.SQS.Model;
using Microsoft.Extensions.Options;
using OtterWorks.NotificationService.Config;
using OtterWorks.NotificationService.Models;

namespace OtterWorks.NotificationService.Services;

public class SqsConsumerService : BackgroundService
{
    private readonly IAmazonSQS _sqsClient;
    private readonly INotificationService _notificationService;
    private readonly AwsSettings _settings;
    private readonly ILogger<SqsConsumerService> _logger;
    private readonly Channel<SqsNotificationMessage> _channel;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };

    public SqsConsumerService(
        IAmazonSQS sqsClient,
        INotificationService notificationService,
        IOptions<AwsSettings> settings,
        ILogger<SqsConsumerService> logger)
    {
        _sqsClient = sqsClient;
        _notificationService = notificationService;
        _settings = settings.Value;
        _logger = logger;
        _channel = Channel.CreateBounded<SqsNotificationMessage>(new BoundedChannelOptions(100)
        {
            FullMode = BoundedChannelFullMode.Wait,
        });
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("SQS Consumer starting, polling: {QueueUrl}", _settings.SqsQueueUrl);

        var processor = Task.Run(() => ProcessChannelAsync(stoppingToken), stoppingToken);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var request = new ReceiveMessageRequest
                {
                    QueueUrl = _settings.SqsQueueUrl,
                    MaxNumberOfMessages = _settings.SqsMaxMessages,
                    WaitTimeSeconds = _settings.SqsWaitTimeSeconds,
                };

                var response = await _sqsClient.ReceiveMessageAsync(request, stoppingToken);

                if (response.Messages.Count > 0)
                {
                    _logger.LogInformation("Received {Count} messages from SQS", response.Messages.Count);
                }

                foreach (var message in response.Messages)
                {
                    var parsed = ParseMessage(message.Body);
                    if (parsed is not null)
                    {
                        await _channel.Writer.WriteAsync(parsed, stoppingToken);

                        await _sqsClient.DeleteMessageAsync(new DeleteMessageRequest
                        {
                            QueueUrl = _settings.SqsQueueUrl,
                            ReceiptHandle = message.ReceiptHandle,
                        }, stoppingToken);

                        _logger.LogDebug("Deleted SQS message: {MessageId}", message.MessageId);
                    }
                    else
                    {
                        _logger.LogWarning("Failed to parse SQS message: {MessageId}", message.MessageId);
                    }
                }

                if (response.Messages.Count == 0)
                {
                    await Task.Delay(_settings.SqsPollIntervalMs, stoppingToken);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error polling SQS");
                await Task.Delay(_settings.SqsPollIntervalMs * 2, stoppingToken);
            }
        }

        _channel.Writer.Complete();
        await processor;
        _logger.LogInformation("SQS Consumer stopping");
    }

    private async Task ProcessChannelAsync(CancellationToken stoppingToken)
    {
        await foreach (var message in _channel.Reader.ReadAllAsync(stoppingToken))
        {
            try
            {
                await _notificationService.ProcessEventAsync(message);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error processing notification event: {EventType}", message.EventType);
            }
        }
    }

    internal static SqsNotificationMessage? ParseMessage(string body)
    {
        try
        {
            var direct = JsonSerializer.Deserialize<SqsNotificationMessage>(body, JsonOptions);
            if (direct is not null && !string.IsNullOrEmpty(direct.EventType))
            {
                return direct;
            }
        }
        catch
        {
            // Fall through to SNS envelope parsing
        }

        try
        {
            var snsEnvelope = JsonSerializer.Deserialize<SnsEnvelope>(body, JsonOptions);
            if (!string.IsNullOrEmpty(snsEnvelope?.Message))
            {
                return JsonSerializer.Deserialize<SqsNotificationMessage>(snsEnvelope.Message, JsonOptions);
            }

            return null;
        }
        catch
        {
            return null;
        }
    }
}
