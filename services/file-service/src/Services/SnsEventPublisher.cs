using System.Text.Json;
using System.Text.Json.Serialization;
using Amazon.SimpleNotificationService;
using Amazon.SimpleNotificationService.Model;
using Microsoft.Extensions.Options;
using OtterWorks.FileService.Config;

namespace OtterWorks.FileService.Services;

public class SnsEventPublisher : IEventPublisher
{
    private readonly IAmazonSimpleNotificationService _snsClient;
    private readonly string? _topicArn;
    private readonly ILogger<SnsEventPublisher> _logger;

    public SnsEventPublisher(
        IAmazonSimpleNotificationService snsClient,
        IOptions<AwsSettings> settings,
        ILogger<SnsEventPublisher> logger)
    {
        _snsClient = snsClient;
        _topicArn = settings.Value.SnsTopicArn;
        _logger = logger;
    }

    public Task FileUploadedAsync(Guid fileId, Guid ownerId, Guid? folderId, string name, string mimeType, long sizeBytes)
    {
        return PublishAsync(new FileEvent
        {
            EventType = "file_uploaded",
            FileId = fileId.ToString(),
            OwnerId = ownerId.ToString(),
            FolderId = folderId?.ToString(),
            Timestamp = DateTime.UtcNow.ToString("o"),
            Name = name,
            MimeType = mimeType,
            SizeBytes = sizeBytes,
        });
    }

    public Task FileDeletedAsync(Guid fileId, Guid ownerId)
    {
        return PublishAsync(new FileEvent
        {
            EventType = "file_deleted",
            FileId = fileId.ToString(),
            OwnerId = ownerId.ToString(),
            Timestamp = DateTime.UtcNow.ToString("o"),
        });
    }

    public Task FileSharedAsync(Guid fileId, Guid ownerId, Guid sharedWith)
    {
        return PublishAsync(new FileEvent
        {
            EventType = "file_shared",
            FileId = fileId.ToString(),
            OwnerId = ownerId.ToString(),
            SharedWithUserId = sharedWith.ToString(),
            Timestamp = DateTime.UtcNow.ToString("o"),
        });
    }

    public Task FileTrashedAsync(Guid fileId, Guid ownerId)
    {
        return PublishAsync(new FileEvent
        {
            EventType = "file_trashed",
            FileId = fileId.ToString(),
            OwnerId = ownerId.ToString(),
            Timestamp = DateTime.UtcNow.ToString("o"),
        });
    }

    public Task FileRestoredAsync(Guid fileId, Guid ownerId, Guid? folderId, string name, string mimeType, long sizeBytes)
    {
        return PublishAsync(new FileEvent
        {
            EventType = "file_restored",
            FileId = fileId.ToString(),
            OwnerId = ownerId.ToString(),
            FolderId = folderId?.ToString(),
            Timestamp = DateTime.UtcNow.ToString("o"),
            Name = name,
            MimeType = mimeType,
            SizeBytes = sizeBytes,
        });
    }

    public Task FileUpdatedAsync(Guid fileId, Guid ownerId, Guid? folderId, string name, string mimeType, long sizeBytes)
    {
        return PublishAsync(new FileEvent
        {
            EventType = "file_updated",
            FileId = fileId.ToString(),
            OwnerId = ownerId.ToString(),
            FolderId = folderId?.ToString(),
            Timestamp = DateTime.UtcNow.ToString("o"),
            Name = name,
            MimeType = mimeType,
            SizeBytes = sizeBytes,
        });
    }

    public Task FileMovedAsync(Guid fileId, Guid ownerId, Guid? folderId)
    {
        return PublishAsync(new FileEvent
        {
            EventType = "file_moved",
            FileId = fileId.ToString(),
            OwnerId = ownerId.ToString(),
            FolderId = folderId?.ToString(),
            Timestamp = DateTime.UtcNow.ToString("o"),
        });
    }

    private async Task PublishAsync(FileEvent fileEvent)
    {
        if (string.IsNullOrEmpty(_topicArn))
        {
            _logger.LogDebug("SNS topic not configured, skipping event publish");
            return;
        }

        var message = JsonSerializer.Serialize(fileEvent);
        var request = new PublishRequest
        {
            TopicArn = _topicArn,
            Message = message,
        };

        if (_topicArn.EndsWith(".fifo", StringComparison.Ordinal))
        {
            request.MessageGroupId = fileEvent.EventType;
            request.MessageDeduplicationId = $"{fileEvent.FileId}_{fileEvent.Timestamp}";
        }

        await _snsClient.PublishAsync(request);
        _logger.LogInformation("Published {EventType} event for file {FileId}", fileEvent.EventType, fileEvent.FileId);
    }
}

internal sealed class FileEvent
{
    [JsonPropertyName("eventType")]
    public string EventType { get; set; } = string.Empty;

    [JsonPropertyName("fileId")]
    public string FileId { get; set; } = string.Empty;

    [JsonPropertyName("ownerId")]
    public string OwnerId { get; set; } = string.Empty;

    [JsonPropertyName("folderId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? FolderId { get; set; }

    [JsonPropertyName("sharedWithUserId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SharedWithUserId { get; set; }

    [JsonPropertyName("timestamp")]
    public string Timestamp { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Name { get; set; }

    [JsonPropertyName("mimeType")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? MimeType { get; set; }

    [JsonPropertyName("sizeBytes")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public long? SizeBytes { get; set; }
}
