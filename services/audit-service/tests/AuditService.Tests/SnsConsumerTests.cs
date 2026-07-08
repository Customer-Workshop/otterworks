using System.Text.Json;
using Amazon.SQS;
using Amazon.SQS.Model;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;
using OtterWorks.AuditService.Config;
using OtterWorks.AuditService.Services;

namespace AuditService.Tests;

public class SnsConsumerTests
{
    private const string QueueName = "otterworks-audit-events-queue";
    private const string QueueUrl = "http://localhost:4566/000000000000/otterworks-audit-events-queue";

    private readonly Mock<IAmazonSQS> _mockSqs = new();
    private readonly Mock<IAuditRepository> _mockRepository = new();
    private readonly Mock<ILogger<SnsConsumer>> _mockLogger = new();
    private readonly IOptions<AwsSettings> _options = Options.Create(new AwsSettings { Region = "us-east-1" });

    private SnsConsumer CreateConsumer() =>
        new(_mockSqs.Object, _mockRepository.Object, _options, _mockLogger.Object);

    private void SetupExistingQueue() =>
        _mockSqs
            .Setup(s => s.GetQueueUrlAsync(QueueName, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new GetQueueUrlResponse { QueueUrl = QueueUrl });

    /// <summary>
    /// Drives the background service through exactly one receive-loop iteration
    /// that returns <paramref name="messages"/>, then blocks so the host can be
    /// stopped deterministically.
    /// </summary>
    private async Task RunOneBatchAsync(params Message[] messages)
    {
        var call = 0;
        _mockSqs
            .Setup(s => s.ReceiveMessageAsync(It.IsAny<ReceiveMessageRequest>(), It.IsAny<CancellationToken>()))
            .Returns(async (ReceiveMessageRequest _, CancellationToken ct) =>
            {
                call++;
                if (call == 1)
                {
                    return new ReceiveMessageResponse { Messages = messages.ToList() };
                }

                await Task.Delay(Timeout.Infinite, ct);
                return new ReceiveMessageResponse { Messages = new List<Message>() };
            });

        _mockSqs
            .Setup(s => s.DeleteMessageAsync(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new DeleteMessageResponse());

        _mockRepository
            .Setup(r => r.SaveEventAsync(It.IsAny<AuditEvent>()))
            .Returns(Task.CompletedTask);

        var consumer = CreateConsumer();
        await consumer.StartAsync(CancellationToken.None);
        await consumer.StopAsync(CancellationToken.None);
    }

    private static Message MessageWith(string body, string messageId = "msg-1") =>
        new() { MessageId = messageId, ReceiptHandle = "receipt-1", Body = body };

    [Fact]
    public async Task ProcessesPlainAuditEventMessage()
    {
        SetupExistingQueue();
        var body = JsonSerializer.Serialize(new
        {
            userId = "user-9",
            action = "update",
            resourceType = "document",
            resourceId = "doc-42",
            ipAddress = "10.0.0.5",
            userAgent = "svc/1.0",
        });

        await RunOneBatchAsync(MessageWith(body, "msg-plain"));

        _mockRepository.Verify(r => r.SaveEventAsync(It.Is<AuditEvent>(e =>
            e.Id == "msg-plain" &&
            e.UserId == "user-9" &&
            e.Action == "update" &&
            e.ResourceType == "document" &&
            e.ResourceId == "doc-42" &&
            e.IpAddress == "10.0.0.5" &&
            e.UserAgent == "svc/1.0")), Times.Once);
        _mockSqs.Verify(s => s.DeleteMessageAsync(QueueUrl, "receipt-1", It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ProcessesFileSharedEventAsShareAction()
    {
        SetupExistingQueue();
        var body = JsonSerializer.Serialize(new
        {
            eventType = "file_shared",
            fileId = "file-77",
            ownerId = "owner-1",
            sharedWithUserId = "user-2",
        });

        await RunOneBatchAsync(MessageWith(body, "msg-share"));

        _mockRepository.Verify(r => r.SaveEventAsync(It.Is<AuditEvent>(e =>
            e.Id == "msg-share" &&
            e.Action == "share" &&
            e.ResourceType == "file" &&
            e.ResourceId == "file-77" &&
            e.UserId == "owner-1" &&
            e.Details != null &&
            e.Details["sharedWithUserId"] == "user-2")), Times.Once);
        _mockSqs.Verify(s => s.DeleteMessageAsync(QueueUrl, "receipt-1", It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task UnwrapsSnsEnvelopeBeforeDeserializing()
    {
        SetupExistingQueue();
        var inner = JsonSerializer.Serialize(new
        {
            userId = "user-inner",
            action = "delete",
            resourceType = "file",
            resourceId = "file-1",
        });
        var envelope = JsonSerializer.Serialize(new { Type = "Notification", Message = inner });

        await RunOneBatchAsync(MessageWith(envelope, "msg-env"));

        _mockRepository.Verify(r => r.SaveEventAsync(It.Is<AuditEvent>(e =>
            e.UserId == "user-inner" &&
            e.Action == "delete" &&
            e.ResourceId == "file-1")), Times.Once);
    }

    [Fact]
    public async Task DefaultsMissingFieldsWhenAuditEventFieldsAreNull()
    {
        SetupExistingQueue();

        await RunOneBatchAsync(MessageWith("{}", "msg-empty"));

        _mockRepository.Verify(r => r.SaveEventAsync(It.Is<AuditEvent>(e =>
            e.UserId == "system" &&
            e.Action == "unknown" &&
            e.ResourceType == "unknown" &&
            e.ResourceId == "")), Times.Once);
        _mockSqs.Verify(s => s.DeleteMessageAsync(QueueUrl, "receipt-1", It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task DeletesButDoesNotSaveWhenPayloadDeserializesToNull()
    {
        SetupExistingQueue();
        var envelope = JsonSerializer.Serialize(new { Message = "null" });

        await RunOneBatchAsync(MessageWith(envelope, "msg-null"));

        _mockRepository.Verify(r => r.SaveEventAsync(It.IsAny<AuditEvent>()), Times.Never);
        _mockSqs.Verify(s => s.DeleteMessageAsync(QueueUrl, "receipt-1", It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task SwallowsInvalidJsonWithoutSavingOrDeleting()
    {
        SetupExistingQueue();

        await RunOneBatchAsync(MessageWith("this-is-not-json", "msg-bad"));

        _mockRepository.Verify(r => r.SaveEventAsync(It.IsAny<AuditEvent>()), Times.Never);
        _mockSqs.Verify(
            s => s.DeleteMessageAsync(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task CreatesQueueWhenItDoesNotExist()
    {
        _mockSqs
            .Setup(s => s.GetQueueUrlAsync(QueueName, It.IsAny<CancellationToken>()))
            .ThrowsAsync(new QueueDoesNotExistException("missing"));
        _mockSqs
            .Setup(s => s.CreateQueueAsync(It.IsAny<CreateQueueRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new CreateQueueResponse { QueueUrl = QueueUrl });

        var body = JsonSerializer.Serialize(new
        {
            userId = "u",
            action = "create",
            resourceType = "file",
            resourceId = "f",
        });

        await RunOneBatchAsync(MessageWith(body, "msg-created"));

        _mockSqs.Verify(
            s => s.CreateQueueAsync(
                It.Is<CreateQueueRequest>(r => r.QueueName == QueueName),
                It.IsAny<CancellationToken>()),
            Times.Once);
        _mockRepository.Verify(r => r.SaveEventAsync(It.IsAny<AuditEvent>()), Times.Once);
    }

    [Fact]
    public async Task StopsWithoutReceivingWhenQueueInitializationFails()
    {
        _mockSqs
            .Setup(s => s.GetQueueUrlAsync(QueueName, It.IsAny<CancellationToken>()))
            .ThrowsAsync(new AmazonSQSException("boom"));

        var consumer = CreateConsumer();
        await consumer.StartAsync(CancellationToken.None);
        await consumer.StopAsync(CancellationToken.None);

        _mockSqs.Verify(
            s => s.ReceiveMessageAsync(It.IsAny<ReceiveMessageRequest>(), It.IsAny<CancellationToken>()),
            Times.Never);
        _mockRepository.Verify(r => r.SaveEventAsync(It.IsAny<AuditEvent>()), Times.Never);
    }
}
