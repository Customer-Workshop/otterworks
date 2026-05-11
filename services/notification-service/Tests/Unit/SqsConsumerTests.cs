using OtterWorks.NotificationService.Services;

namespace NotificationService.Tests.Unit;

public class SqsConsumerTests
{
    [Fact]
    public void ParseMessage_ParsesDirectSqsMessage()
    {
        var body = @"{
            ""eventType"": ""file_shared"",
            ""fileId"": ""file-123"",
            ""ownerId"": ""owner-1"",
            ""sharedWithUserId"": ""user-2"",
            ""timestamp"": ""2024-01-01T00:00:00Z""
        }";

        var result = SqsConsumerService.ParseMessage(body);

        Assert.NotNull(result);
        Assert.Equal("file_shared", result.EventType);
        Assert.Equal("file-123", result.FileId);
        Assert.Equal("owner-1", result.OwnerId);
        Assert.Equal("user-2", result.SharedWithUserId);
    }

    [Fact]
    public void ParseMessage_ParsesSnsWrappedMessage()
    {
        var innerMessage = @"{""eventType"":""comment_added"",""userId"":""user-1"",""actorId"":""actor-1"",""documentId"":""doc-1"",""commentId"":""c-1"",""timestamp"":""2024-01-01T00:00:00Z""}";
        var escapedInner = innerMessage.Replace("\"", "\\\"");
        var body = $@"{{
            ""Type"": ""Notification"",
            ""MessageId"": ""msg-123"",
            ""TopicArn"": ""arn:aws:sns:us-east-1:000000000000:test-topic"",
            ""Message"": ""{escapedInner}""
        }}";

        var result = SqsConsumerService.ParseMessage(body);

        Assert.NotNull(result);
        Assert.Equal("comment_added", result.EventType);
        Assert.Equal("user-1", result.UserId);
        Assert.Equal("actor-1", result.ActorId);
        Assert.Equal("doc-1", result.DocumentId);
        Assert.Equal("c-1", result.CommentId);
    }

    [Fact]
    public void ParseMessage_ReturnsNull_ForInvalidJson()
    {
        var result = SqsConsumerService.ParseMessage("not json at all");
        Assert.Null(result);
    }

    [Fact]
    public void ParseMessage_ParsesDocumentEditedEvent()
    {
        var body = @"{
            ""eventType"": ""document_edited"",
            ""userId"": ""user-1"",
            ""actorId"": ""editor-1"",
            ""documentId"": ""doc-456"",
            ""timestamp"": ""2024-06-15T10:30:00Z""
        }";

        var result = SqsConsumerService.ParseMessage(body);

        Assert.NotNull(result);
        Assert.Equal("document_edited", result.EventType);
        Assert.Equal("doc-456", result.DocumentId);
        Assert.Equal("editor-1", result.ActorId);
    }

    [Fact]
    public void ParseMessage_ParsesUserMentionedEvent()
    {
        var body = @"{
            ""eventType"": ""user_mentioned"",
            ""mentionedUserId"": ""mentioned-user"",
            ""actorId"": ""actor-2"",
            ""documentId"": ""doc-789"",
            ""timestamp"": ""2024-06-15T10:30:00Z""
        }";

        var result = SqsConsumerService.ParseMessage(body);

        Assert.NotNull(result);
        Assert.Equal("user_mentioned", result.EventType);
        Assert.Equal("mentioned-user", result.MentionedUserId);
        Assert.Equal("actor-2", result.ActorId);
        Assert.Equal("doc-789", result.DocumentId);
    }

    [Fact]
    public void ParseMessage_HandlesMissingOptionalFields()
    {
        var body = @"{
            ""eventType"": ""file_shared"",
            ""timestamp"": ""2024-01-01T00:00:00Z""
        }";

        var result = SqsConsumerService.ParseMessage(body);

        Assert.NotNull(result);
        Assert.Equal("file_shared", result.EventType);
        Assert.Equal(string.Empty, result.FileId);
        Assert.Equal(string.Empty, result.OwnerId);
        Assert.Equal(string.Empty, result.SharedWithUserId);
    }
}
