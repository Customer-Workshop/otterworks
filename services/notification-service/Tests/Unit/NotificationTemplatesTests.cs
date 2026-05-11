using OtterWorks.NotificationService.Models;
using OtterWorks.NotificationService.Services;

namespace NotificationService.Tests.Unit;

public class NotificationTemplatesTests
{
    [Fact]
    public void Render_FileSharedEvent()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "file_shared",
            FileId = "file-abc",
            OwnerId = "alice",
            SharedWithUserId = "bob",
            Timestamp = "2024-01-01T00:00:00Z",
        };

        var rendered = NotificationTemplates.Render(sqsEvent);

        Assert.Equal("File Shared With You", rendered.Title);
        Assert.Contains("alice", rendered.Message);
        Assert.Equal("OtterWorks: A file has been shared with you", rendered.EmailSubject);
        Assert.Contains("file-abc", rendered.EmailBody);
        Assert.Contains("alice", rendered.EmailBody);
    }

    [Fact]
    public void Render_CommentAddedEvent()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "comment_added",
            ActorId = "commenter-1",
            DocumentId = "doc-123",
            CommentId = "c-1",
            UserId = "owner-1",
            Timestamp = "2024-01-01T00:00:00Z",
        };

        var rendered = NotificationTemplates.Render(sqsEvent);

        Assert.Equal("New Comment", rendered.Title);
        Assert.Contains("commenter-1", rendered.Message);
        Assert.Contains("doc-123", rendered.Message);
    }

    [Fact]
    public void Render_DocumentEditedEvent()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "document_edited",
            ActorId = "editor-1",
            DocumentId = "doc-456",
            UserId = "owner-1",
            Timestamp = "2024-01-01T00:00:00Z",
        };

        var rendered = NotificationTemplates.Render(sqsEvent);

        Assert.Equal("Document Edited", rendered.Title);
        Assert.Contains("editor-1", rendered.Message);
        Assert.Contains("doc-456", rendered.Message);
    }

    [Fact]
    public void Render_UserMentionedEvent()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "user_mentioned",
            ActorId = "mentioner-1",
            DocumentId = "doc-789",
            MentionedUserId = "mentioned-user",
            Timestamp = "2024-01-01T00:00:00Z",
        };

        var rendered = NotificationTemplates.Render(sqsEvent);

        Assert.Equal("You Were Mentioned", rendered.Title);
        Assert.Contains("mentioner-1", rendered.Message);
        Assert.Contains("doc-789", rendered.Message);
    }

    [Fact]
    public void Render_UnknownEventType_ReturnsDefault()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "unknown_event",
            Timestamp = "2024-01-01T00:00:00Z",
        };

        var rendered = NotificationTemplates.Render(sqsEvent);

        Assert.Equal("Notification", rendered.Title);
        Assert.Equal("You have a new notification.", rendered.Message);
    }

    [Fact]
    public void Render_UsesOwnerIdAsFallbackForActorId()
    {
        var sqsEvent = new SqsNotificationMessage
        {
            EventType = "file_shared",
            FileId = "file-xyz",
            OwnerId = "fallback-owner",
            SharedWithUserId = "bob",
            ActorId = string.Empty,
            Timestamp = "2024-01-01T00:00:00Z",
        };

        var rendered = NotificationTemplates.Render(sqsEvent);

        Assert.Contains("fallback-owner", rendered.Message);
    }
}
