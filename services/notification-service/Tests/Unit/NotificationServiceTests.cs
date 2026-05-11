using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.NotificationService.Models;
using OtterWorks.NotificationService.Services;

namespace NotificationService.Tests.Unit;

public class NotificationServiceTests
{
    private readonly Mock<INotificationRepository> _repository = new();
    private readonly Mock<ILogger<OtterWorks.NotificationService.Services.NotificationService>> _logger = new();
    private readonly OtterWorks.NotificationService.Services.NotificationService _service;

    public NotificationServiceTests()
    {
        _service = new OtterWorks.NotificationService.Services.NotificationService(_repository.Object, _logger.Object);
    }

    [Fact]
    public void ResolveTargetUserId_ReturnsSharedWithUserId_ForFileSharedEvents()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "file_shared",
            FileId = "file-123",
            OwnerId = "owner-1",
            SharedWithUserId = "user-2",
            Timestamp = "2024-01-01T00:00:00Z",
        };
        Assert.Equal("user-2", OtterWorks.NotificationService.Services.NotificationService.ResolveTargetUserId(sqsEvent));
    }

    [Fact]
    public void ResolveTargetUserId_ReturnsMentionedUserId_ForUserMentionedEvents()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "user_mentioned",
            MentionedUserId = "mentioned-user",
            ActorId = "actor-1",
            DocumentId = "doc-1",
            Timestamp = "2024-01-01T00:00:00Z",
        };
        Assert.Equal("mentioned-user", OtterWorks.NotificationService.Services.NotificationService.ResolveTargetUserId(sqsEvent));
    }

    [Fact]
    public void ResolveTargetUserId_ReturnsUserId_ForCommentAddedEvents()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "comment_added",
            UserId = "doc-owner",
            ActorId = "commenter",
            DocumentId = "doc-1",
            CommentId = "comment-1",
            Timestamp = "2024-01-01T00:00:00Z",
        };
        Assert.Equal("doc-owner", OtterWorks.NotificationService.Services.NotificationService.ResolveTargetUserId(sqsEvent));
    }

    [Fact]
    public void ResolveTargetUserId_ReturnsUserId_ForDocumentEditedEvents()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "document_edited",
            UserId = "doc-owner",
            ActorId = "editor",
            DocumentId = "doc-1",
            Timestamp = "2024-01-01T00:00:00Z",
        };
        Assert.Equal("doc-owner", OtterWorks.NotificationService.Services.NotificationService.ResolveTargetUserId(sqsEvent));
    }

    [Fact]
    public void ResolveResourceId_ReturnsFileId_ForFileShared()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "file_shared",
            FileId = "file-abc",
            Timestamp = "2024-01-01T00:00:00Z",
        };
        Assert.Equal("file-abc", OtterWorks.NotificationService.Services.NotificationService.ResolveResourceId(sqsEvent));
    }

    [Fact]
    public void ResolveResourceId_ReturnsCommentId_ForCommentAdded()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "comment_added",
            CommentId = "comment-xyz",
            DocumentId = "doc-1",
            Timestamp = "2024-01-01T00:00:00Z",
        };
        Assert.Equal("comment-xyz", OtterWorks.NotificationService.Services.NotificationService.ResolveResourceId(sqsEvent));
    }

    [Fact]
    public void ResolveResourceId_ReturnsDocumentId_ForDocumentEdited()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "document_edited",
            DocumentId = "doc-123",
            Timestamp = "2024-01-01T00:00:00Z",
        };
        Assert.Equal("doc-123", OtterWorks.NotificationService.Services.NotificationService.ResolveResourceId(sqsEvent));
    }

    [Fact]
    public void ResolveResourceType_ReturnsCorrectTypes()
    {
        Assert.Equal("file", OtterWorks.NotificationService.Services.NotificationService.ResolveResourceType(
            new SqsNotificationMessage { EventType = "file_shared", Timestamp = "2024-01-01T00:00:00Z" }));
        Assert.Equal("comment", OtterWorks.NotificationService.Services.NotificationService.ResolveResourceType(
            new SqsNotificationMessage { EventType = "comment_added", Timestamp = "2024-01-01T00:00:00Z" }));
        Assert.Equal("document", OtterWorks.NotificationService.Services.NotificationService.ResolveResourceType(
            new SqsNotificationMessage { EventType = "document_edited", Timestamp = "2024-01-01T00:00:00Z" }));
        Assert.Equal("document", OtterWorks.NotificationService.Services.NotificationService.ResolveResourceType(
            new SqsNotificationMessage { EventType = "user_mentioned", Timestamp = "2024-01-01T00:00:00Z" }));
        Assert.Equal("unknown", OtterWorks.NotificationService.Services.NotificationService.ResolveResourceType(
            new SqsNotificationMessage { EventType = "other_event", Timestamp = "2024-01-01T00:00:00Z" }));
    }

    [Fact]
    public async Task ProcessEvent_StoresInAppNotification_ForFileShared()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "file_shared",
            FileId = "file-123",
            OwnerId = "owner-1",
            SharedWithUserId = "user-2",
            Timestamp = "2024-01-01T00:00:00Z",
        };

        _repository.Setup(r => r.GetPreferencesAsync("user-2"))
            .ReturnsAsync(new NotificationPreference { UserId = "user-2" });

        Notification? savedNotification = null;
        _repository.Setup(r => r.SaveNotificationAsync(It.IsAny<Notification>()))
            .Callback<Notification>(n => savedNotification = n)
            .Returns(Task.CompletedTask);

        await _service.ProcessEventAsync(sqsEvent);

        _repository.Verify(r => r.SaveNotificationAsync(It.IsAny<Notification>()), Times.AtLeastOnce());
        Assert.NotNull(savedNotification);
        Assert.Equal("user-2", savedNotification.UserId);
        Assert.Equal("file_shared", savedNotification.Type);
        Assert.Equal("File Shared With You", savedNotification.Title);
        Assert.Contains("in_app", savedNotification.DeliveredVia);
    }

    [Fact]
    public async Task ProcessEvent_SkipsEmail_WhenNotInPreferences()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "document_edited",
            UserId = "user-1",
            ActorId = "editor-1",
            DocumentId = "doc-1",
            Timestamp = "2024-01-01T00:00:00Z",
        };

        var prefs = new NotificationPreference
        {
            UserId = "user-1",
            Channels = new Dictionary<string, List<DeliveryChannel>>
            {
                ["document_edited"] = new List<DeliveryChannel> { DeliveryChannel.IN_APP },
            },
        };
        _repository.Setup(r => r.GetPreferencesAsync("user-1")).ReturnsAsync(prefs);

        Notification? savedNotification = null;
        _repository.Setup(r => r.SaveNotificationAsync(It.IsAny<Notification>()))
            .Callback<Notification>(n => savedNotification = n)
            .Returns(Task.CompletedTask);

        await _service.ProcessEventAsync(sqsEvent);

        _repository.Verify(r => r.SaveNotificationAsync(It.IsAny<Notification>()), Times.AtLeastOnce());
        Assert.NotNull(savedNotification);
        Assert.DoesNotContain("email", savedNotification.DeliveredVia);
    }

    [Fact]
    public async Task ProcessEvent_DoesNothing_ForBlankTargetUser()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "file_shared",
            FileId = "file-123",
            OwnerId = "owner-1",
            SharedWithUserId = string.Empty,
            Timestamp = "2024-01-01T00:00:00Z",
        };

        await _service.ProcessEventAsync(sqsEvent);

        _repository.Verify(r => r.SaveNotificationAsync(It.IsAny<Notification>()), Times.Never());
    }

    [Fact]
    public async Task GetNotifications_DelegatesToRepository()
    {
        var notifications = new List<Notification>
        {
            new Notification
            {
                Id = "n-1",
                UserId = "user-1",
                Type = "file_shared",
                Title = "Test",
                Message = "Test msg",
                CreatedAt = "2024-01-01T00:00:00Z",
            },
        };
        _repository.Setup(r => r.GetNotificationsByUserIdAsync("user-1", 1, 20))
            .ReturnsAsync((notifications, 1));

        var (result, total) = await _service.GetNotificationsAsync("user-1", 1, 20);
        Assert.Single(result);
        Assert.Equal(1, total);
        Assert.Equal("n-1", result[0].Id);
    }

    [Fact]
    public async Task MarkAsRead_DelegatesToRepository()
    {
        _repository.Setup(r => r.MarkAsReadAsync("n-1")).ReturnsAsync(true);
        Assert.True(await _service.MarkAsReadAsync("n-1"));
    }

    [Fact]
    public async Task MarkAllAsRead_DelegatesToRepository()
    {
        _repository.Setup(r => r.MarkAllAsReadAsync("user-1")).ReturnsAsync(5);
        Assert.Equal(5, await _service.MarkAllAsReadAsync("user-1"));
    }

    [Fact]
    public async Task GetUnreadCount_DelegatesToRepository()
    {
        _repository.Setup(r => r.GetUnreadCountAsync("user-1")).ReturnsAsync(3);
        Assert.Equal(3, await _service.GetUnreadCountAsync("user-1"));
    }

    [Fact]
    public async Task ProcessEvent_IncludesPush_WhenPushChannelEnabled()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "user_mentioned",
            MentionedUserId = "user-3",
            ActorId = "actor-1",
            DocumentId = "doc-1",
            Timestamp = "2024-01-01T00:00:00Z",
        };

        _repository.Setup(r => r.GetPreferencesAsync("user-3"))
            .ReturnsAsync(new NotificationPreference { UserId = "user-3" });

        Notification? lastSavedNotification = null;
        _repository.Setup(r => r.SaveNotificationAsync(It.IsAny<Notification>()))
            .Callback<Notification>(n => lastSavedNotification = n)
            .Returns(Task.CompletedTask);

        await _service.ProcessEventAsync(sqsEvent);

        Assert.NotNull(lastSavedNotification);
        Assert.Contains("push", lastSavedNotification.DeliveredVia);
    }
}
