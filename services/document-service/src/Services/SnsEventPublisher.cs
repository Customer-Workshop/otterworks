using System.Text.Json;
using Amazon.SimpleNotificationService;
using Amazon.SimpleNotificationService.Model;
using Microsoft.Extensions.Options;
using OtterWorks.DocumentService.Config;

namespace OtterWorks.DocumentService.Services;

public class SnsEventPublisher : IEventPublisher
{
    private readonly IAmazonSimpleNotificationService _snsClient;
    private readonly AwsSettings _settings;
    private readonly ILogger<SnsEventPublisher> _logger;

    public SnsEventPublisher(
        IAmazonSimpleNotificationService snsClient,
        IOptions<AwsSettings> settings,
        ILogger<SnsEventPublisher> logger)
    {
        _snsClient = snsClient;
        _settings = settings.Value;
        _logger = logger;
    }

    public async Task PublishAsync(string eventType, Dictionary<string, object> payload)
    {
        if (!_settings.SnsEnabled)
        {
            _logger.LogInformation("SNS event skipped: {EventType}", eventType);
            return;
        }

        var message = new Dictionary<string, object>
        {
            ["event_type"] = eventType,
            ["timestamp"] = DateTime.UtcNow.ToString("O"),
            ["payload"] = payload,
        };

        try
        {
            var request = new PublishRequest
            {
                TopicArn = _settings.SnsTopicArn,
                Message = JsonSerializer.Serialize(message),
                MessageAttributes = new Dictionary<string, MessageAttributeValue>
                {
                    ["event_type"] = new MessageAttributeValue
                    {
                        DataType = "String",
                        StringValue = eventType,
                    },
                },
            };

            await _snsClient.PublishAsync(request);
            _logger.LogInformation("SNS event published: {EventType}", eventType);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "SNS publish failed: {EventType}", eventType);
        }
    }
}
