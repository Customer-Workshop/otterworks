using System.Text.Json;
using Amazon.SQS;
using Amazon.SQS.Model;
using Microsoft.Extensions.Options;
using OtterWorks.SearchService.Configuration;
namespace OtterWorks.SearchService.Services;

public class SqsConsumerService : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly SqsSettings _settings;
    private readonly Serilog.ILogger _logger = Serilog.Log.ForContext<SqsConsumerService>();

    public SqsConsumerService(IServiceScopeFactory scopeFactory, IOptions<SqsSettings> settings)
    {
        _scopeFactory = scopeFactory;
        _settings = settings.Value;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_settings.Enabled || string.IsNullOrEmpty(_settings.QueueUrl))
        {
            _logger.Warning("SQS consumer skipped: no queue URL configured or not enabled");
            return;
        }

        _logger.Information("SQS consumer started: {QueueUrl}", _settings.QueueUrl);

        var config = new AmazonSQSConfig { RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(_settings.Region) };
        if (!string.IsNullOrEmpty(_settings.EndpointUrl))
            config.ServiceURL = _settings.EndpointUrl;

        using var sqsClient = new AmazonSQSClient(config);

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

                var response = await sqsClient.ReceiveMessageAsync(request, stoppingToken);

                foreach (var message in response.Messages)
                {
                    await ProcessMessageAsync(sqsClient, message, stoppingToken);
                }
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.Error(ex, "SQS consumer error");
                await Task.Delay(5000, stoppingToken);
            }
        }

        _logger.Information("SQS consumer stopped");
    }

    public static Dictionary<string, object?> NormalizeEvent(Dictionary<string, object?> body)
    {
        if (body.TryGetValue("event_type", out var eventTypeVal) && body.TryGetValue("payload", out var payloadVal))
        {
            string eventType = eventTypeVal?.ToString() ?? string.Empty;
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
                ["data"] = payloadVal,
            };
        }

        if (body.TryGetValue("eventType", out var camelEventTypeVal))
        {
            string eventType = camelEventTypeVal?.ToString() ?? string.Empty;
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
                return body;

            if (action == "delete")
            {
                return new Dictionary<string, object?>
                {
                    ["action"] = "delete",
                    ["data"] = new Dictionary<string, object?>
                    {
                        ["type"] = "file",
                        ["id"] = GetStr(body, "fileId"),
                    },
                };
            }

            return new Dictionary<string, object?>
            {
                ["action"] = action,
                ["data"] = new Dictionary<string, object?>
                {
                    ["id"] = GetStr(body, "fileId"),
                    ["name"] = GetStr(body, "name"),
                    ["mime_type"] = GetStr(body, "mimeType"),
                    ["owner_id"] = GetStr(body, "ownerId"),
                    ["folder_id"] = GetStr(body, "folderId"),
                    ["size"] = GetIntVal(body, "sizeBytes"),
                    ["tags"] = GetTagsList(body),
                    ["created_at"] = GetStr(body, "timestamp"),
                    ["updated_at"] = GetStr(body, "timestamp"),
                },
            };
        }

        return body;
    }

    private async Task ProcessMessageAsync(AmazonSQSClient sqs, Message message, CancellationToken ct)
    {
        try
        {
            var body = JsonSerializer.Deserialize<Dictionary<string, object?>>(message.Body) ?? new();

            if (body.TryGetValue("Message", out var msgVal) && body.ContainsKey("TopicArn"))
            {
                body = JsonSerializer.Deserialize<Dictionary<string, object?>>(msgVal?.ToString() ?? "{}") ?? new();
            }

            body = NormalizeEvent(body);

            using var scope = _scopeFactory.CreateScope();
            var indexer = scope.ServiceProvider.GetRequiredService<IIndexerService>();
            var result = indexer.ProcessEvent(body);
            _logger.Information("SQS message processed: {Result}", result);

            await sqs.DeleteMessageAsync(_settings.QueueUrl, message.ReceiptHandle, ct);
        }
        catch (JsonException)
        {
            _logger.Error("SQS message invalid JSON: {MessageId}", message.MessageId);
            await sqs.DeleteMessageAsync(_settings.QueueUrl, message.ReceiptHandle, ct);
        }
        catch (ArgumentException)
        {
            _logger.Error("SQS message validation failed: {MessageId}", message.MessageId);
            await sqs.DeleteMessageAsync(_settings.QueueUrl, message.ReceiptHandle, ct);
        }
        catch (Exception ex)
        {
            _logger.Error(ex, "SQS message processing failed: {MessageId}", message.MessageId);
        }
    }

    private static string GetStr(Dictionary<string, object?> dict, string key)
    {
        if (!dict.TryGetValue(key, out var val) || val is null) return string.Empty;
        if (val is JsonElement je) return je.GetString() ?? string.Empty;
        return val.ToString() ?? string.Empty;
    }

    private static object GetIntVal(Dictionary<string, object?> dict, string key)
    {
        if (!dict.TryGetValue(key, out var val) || val is null) return 0;
        if (val is JsonElement je && je.ValueKind == JsonValueKind.Number) return je.GetInt32();
        if (val is int i) return i;
        if (int.TryParse(val.ToString(), out var p)) return p;
        return 0;
    }

    private static List<string> GetTagsList(Dictionary<string, object?> dict)
    {
        if (!dict.TryGetValue("tags", out var val) || val is null) return new List<string>();
        if (val is JsonElement je && je.ValueKind == JsonValueKind.Array)
            return je.EnumerateArray().Select(e => e.GetString() ?? string.Empty).ToList();
        return new List<string>();
    }
}
