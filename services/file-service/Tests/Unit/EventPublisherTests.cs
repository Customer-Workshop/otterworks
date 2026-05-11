using System.Text.Json;
using Amazon.SimpleNotificationService;
using Amazon.SimpleNotificationService.Model;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Moq;
using OtterWorks.FileService.Config;
using OtterWorks.FileService.Services;

namespace FileService.Tests.Unit;

public class EventPublisherTests
{
    private readonly Mock<IAmazonSimpleNotificationService> _mockSns;
    private readonly IOptions<AwsSettings> _options;
    private readonly SnsEventPublisher _publisher;

    public EventPublisherTests()
    {
        _mockSns = new Mock<IAmazonSimpleNotificationService>();
        _options = Options.Create(new AwsSettings
        {
            SnsTopicArn = "arn:aws:sns:us-east-1:000000000000:test-topic",
        });
        _publisher = new SnsEventPublisher(
            _mockSns.Object,
            _options,
            Mock.Of<ILogger<SnsEventPublisher>>());
    }

    [Fact]
    public async Task FileUploaded_PublishesCorrectEvent()
    {
        _mockSns
            .Setup(s => s.PublishAsync(It.IsAny<PublishRequest>(), default))
            .ReturnsAsync(new PublishResponse());

        var fileId = Guid.NewGuid();
        var ownerId = Guid.NewGuid();

        await _publisher.FileUploadedAsync(fileId, ownerId, null, "test.txt", "text/plain", 100);

        _mockSns.Verify(s => s.PublishAsync(
            It.Is<PublishRequest>(r =>
                r.Message.Contains("file_uploaded") &&
                r.Message.Contains("fileId") &&
                r.Message.Contains("ownerId")),
            default), Times.Once);
    }

    [Fact]
    public async Task FileEvent_WithFolder_IncludesFolderId()
    {
        _mockSns
            .Setup(s => s.PublishAsync(It.IsAny<PublishRequest>(), default))
            .ReturnsAsync(new PublishResponse());

        var fileId = Guid.NewGuid();
        var ownerId = Guid.NewGuid();
        var folderId = Guid.NewGuid();

        await _publisher.FileMovedAsync(fileId, ownerId, folderId);

        _mockSns.Verify(s => s.PublishAsync(
            It.Is<PublishRequest>(r => r.Message.Contains(folderId.ToString())),
            default), Times.Once);
    }

    [Fact]
    public async Task NoTopicConfigured_SkipsPublish()
    {
        var options = Options.Create(new AwsSettings { SnsTopicArn = null });
        var publisher = new SnsEventPublisher(
            _mockSns.Object,
            options,
            Mock.Of<ILogger<SnsEventPublisher>>());

        await publisher.FileDeletedAsync(Guid.NewGuid(), Guid.NewGuid());

        _mockSns.Verify(s => s.PublishAsync(It.IsAny<PublishRequest>(), default), Times.Never);
    }
}
