using System.Text.Json;
using Amazon.SQS;
using Amazon.SQS.Model;
using Microsoft.Extensions.Options;
using OtterWorks.SearchService.Config;

namespace OtterWorks.SearchService.Services;

public class SqsConsumer : BackgroundService
{
    private readonly IAmazonSQS _sqsClient;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly SqsSettings _settings;
    private readonly ILogger<SqsConsumer> _logger;

    public SqsConsumer(
        IAmazonSQS sqsClient,
        IServiceScopeFactory scopeFactory,
        IOptions<SqsSettings> settings,
        ILogger<SqsConsumer> logger)
    {
        _sqsClient = sqsClient;
        _scopeFactory = scopeFactory;
        _settings = settings.Value;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_settings.Enabled || string.IsNullOrEmpty(_settings.QueueUrl))
        {
            _logger.LogWarning("SQS consumer skipped: not enabled or no queue URL configured");
            return;
        }

        _logger.LogInformation("SQS consumer started, queue: {QueueUrl}", _settings.QueueUrl);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var request = new ReceiveMessageRequest
                {
                    QueueUrl = _settings.QueueUrl,
                    MaxNumberOfMessages = _settings.MaxMessages,
                    WaitTimeSeconds = _settings.WaitTimeSeconds,
                    VisibilityTimeout = _settings.VisibilityTimeout,
                };

                var response = await _sqsClient.ReceiveMessageAsync(request, stoppingToken);

                foreach (var message in response.Messages)
                {
                    await ProcessMessageAsync(message, stoppingToken);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "SQS consumer error");
                await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
            }
        }

        _logger.LogInformation("SQS consumer stopping");
    }

    private async Task ProcessMessageAsync(Message message, CancellationToken ct)
    {
        try
        {
            var body = message.Body;

            Dictionary<string, object?>? parsed;
            try
            {
                parsed = JsonSerializer.Deserialize<Dictionary<string, object?>>(body);
            }
            catch (JsonException)
            {
                _logger.LogError("SQS message invalid JSON: {MessageId}", message.MessageId);
                await DeleteMessageAsync(message.ReceiptHandle, ct);
                return;
            }

            if (parsed is null)
            {
                await DeleteMessageAsync(message.ReceiptHandle, ct);
                return;
            }

            // Handle SNS-wrapped messages
            if (parsed.TryGetValue("Message", out var snsMsg) &&
                parsed.ContainsKey("TopicArn") &&
                snsMsg is JsonElement snsEl && snsEl.ValueKind == JsonValueKind.String)
            {
                var innerBody = snsEl.GetString();
                if (!string.IsNullOrEmpty(innerBody))
                {
                    parsed = JsonSerializer.Deserialize<Dictionary<string, object?>>(innerBody);
                    if (parsed is null)
                    {
                        await DeleteMessageAsync(message.ReceiptHandle, ct);
                        return;
                    }
                }
            }

            var normalized = NormalizeEvent(parsed);

            using var scope = _scopeFactory.CreateScope();
            var indexer = scope.ServiceProvider.GetRequiredService<IIndexer>();
            var result = await indexer.ProcessEventAsync(normalized, ct);
            _logger.LogInformation("SQS message processed: {Result}", result?.Status ?? "skipped");

            await DeleteMessageAsync(message.ReceiptHandle, ct);
        }
        catch (ArgumentException)
        {
            _logger.LogError("SQS message validation failed: {MessageId}", message.MessageId);
            await DeleteMessageAsync(message.ReceiptHandle, ct);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "SQS message processing failed: {MessageId}", message.MessageId);
        }
    }

    internal static Dictionary<string, object?> NormalizeEvent(Dictionary<string, object?> body)
    {
        // Format 1: snake_case with nested payload (document-service)
        if (body.TryGetValue("event_type", out var eventTypeObj) &&
            body.TryGetValue("payload", out var payloadValue))
        {
            var eventType = eventTypeObj is JsonElement etEl && etEl.ValueKind == JsonValueKind.String
                ? etEl.GetString() ?? string.Empty
                : eventTypeObj?.ToString() ?? string.Empty;

            var actionMap = new Dictionary<string, string>
            {
                ["document_created"] = "index_document",
                ["document_updated"] = "index_document",
                ["document_deleted"] = "delete",
                ["file_created"] = "index_file",
                ["file_uploaded"] = "index_file",
                ["file_updated"] = "index_file",
                ["file_deleted"] = "delete",
                ["file_trashed"] = "delete",
                ["file_restored"] = "index_file",
            };

            return new Dictionary<string, object?>
            {
                ["action"] = actionMap.GetValueOrDefault(eventType, eventType),
                ["data"] = payloadValue,
            };
        }

        // Format 2: camelCase flat event from file-service
        if (body.TryGetValue("eventType", out var camelEventTypeObj))
        {
            var eventType = camelEventTypeObj is JsonElement ceEl && ceEl.ValueKind == JsonValueKind.String
                ? ceEl.GetString() ?? string.Empty
                : camelEventTypeObj?.ToString() ?? string.Empty;

            var actionMap = new Dictionary<string, string>
            {
                ["file_uploaded"] = "index_file",
                ["file_created"] = "index_file",
                ["file_updated"] = "index_file",
                ["file_deleted"] = "delete",
                ["file_trashed"] = "delete",
                ["file_restored"] = "index_file",
            };

            if (!actionMap.TryGetValue(eventType, out var action))
            {
                return body;
            }

            if (action == "delete")
            {
                var fileId = body.TryGetValue("fileId", out var fidObj)
                    ? (fidObj is JsonElement fidEl && fidEl.ValueKind == JsonValueKind.String ? fidEl.GetString() : fidObj?.ToString()) ?? string.Empty
                    : string.Empty;

                return new Dictionary<string, object?>
                {
                    ["action"] = "delete",
                    ["data"] = new Dictionary<string, object?> { ["type"] = "file", ["id"] = fileId },
                };
            }

            var timestamp = body.TryGetValue("timestamp", out var tsObj)
                ? (tsObj is JsonElement tsEl && tsEl.ValueKind == JsonValueKind.String ? tsEl.GetString() : tsObj?.ToString())
                : null;

            var data = new Dictionary<string, object?>
            {
                ["id"] = GetJsonValue(body, "fileId"),
                ["name"] = GetJsonValue(body, "name"),
                ["mime_type"] = GetJsonValue(body, "mimeType"),
                ["owner_id"] = GetJsonValue(body, "ownerId"),
                ["folder_id"] = GetJsonValue(body, "folderId"),
                ["size"] = body.TryGetValue("sizeBytes", out var sbObj) ? sbObj : 0,
                ["tags"] = body.TryGetValue("tags", out var tagsObj) ? tagsObj : new List<string>(),
                ["created_at"] = timestamp,
                ["updated_at"] = timestamp,
            };

            return new Dictionary<string, object?> { ["action"] = action, ["data"] = data };
        }

        // Format 3: already in indexer format
        return body;
    }

    private static string? GetJsonValue(Dictionary<string, object?> dict, string key)
    {
        if (!dict.TryGetValue(key, out var value))
        {
            return string.Empty;
        }

        if (value is JsonElement je && je.ValueKind == JsonValueKind.String)
        {
            return je.GetString();
        }

        return value?.ToString() ?? string.Empty;
    }

    private async Task DeleteMessageAsync(string receiptHandle, CancellationToken ct)
    {
        await _sqsClient.DeleteMessageAsync(_settings.QueueUrl, receiptHandle, ct);
    }
}
