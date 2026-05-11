using FluentAssertions;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.CollabService.Models;
using OtterWorks.CollabService.Services;

namespace CollabService.Tests.Unit;

public class AwarenessServiceTests
{
    private readonly AwarenessService awareness;

    public AwarenessServiceTests()
    {
        var logger = new Mock<ILogger<AwarenessService>>();
        awareness = new AwarenessService(logger.Object);
    }

    [Fact]
    public void AddUser_ShouldAddUserToDocument()
    {
        UserAwareness result = awareness.AddUser("doc-1", "socket-1", "user-1", "Alice", "alice@test.com");

        result.UserId.Should().Be("user-1");
        result.DisplayName.Should().Be("Alice");
        result.Email.Should().Be("alice@test.com");
        result.Color.Should().NotBeNullOrEmpty();
        result.Cursor.Should().BeNull();
        result.Selection.Should().BeNull();
        result.IsTyping.Should().BeFalse();
        result.LastActive.Should().BeGreaterThan(0);
    }

    [Fact]
    public void AddUser_ShouldAssignDifferentColorsToUsers()
    {
        UserAwareness user1 = awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");
        UserAwareness user2 = awareness.AddUser("doc-1", "s2", "u2", "Bob", "b@t.com");

        user1.Color.Should().NotBe(user2.Color);
    }

    [Fact]
    public void AddUser_ShouldTrackUserCountPerDocument()
    {
        awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");
        awareness.AddUser("doc-1", "s2", "u2", "Bob", "b@t.com");
        awareness.AddUser("doc-2", "s3", "u3", "Charlie", "c@t.com");

        awareness.GetDocumentUserCount("doc-1").Should().Be(2);
        awareness.GetDocumentUserCount("doc-2").Should().Be(1);
        awareness.GetDocumentUserCount("doc-3").Should().Be(0);
    }

    [Fact]
    public void RemoveUser_ShouldRemoveUserAndReturnMapping()
    {
        awareness.AddUser("doc-1", "socket-1", "user-1", "Alice", "a@t.com");

        (string DocumentId, string UserId)? result = awareness.RemoveUser("socket-1");

        result.Should().NotBeNull();
        result!.Value.DocumentId.Should().Be("doc-1");
        result!.Value.UserId.Should().Be("user-1");
        awareness.GetDocumentUserCount("doc-1").Should().Be(0);
    }

    [Fact]
    public void RemoveUser_ShouldReturnNullForUnknownSocket()
    {
        (string DocumentId, string UserId)? result = awareness.RemoveUser("unknown-socket");
        result.Should().BeNull();
    }

    [Fact]
    public void RemoveUser_ShouldCleanUpEmptyDocumentStates()
    {
        awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");
        awareness.RemoveUser("s1");

        awareness.GetActiveDocumentIds().Should().NotContain("doc-1");
    }

    [Fact]
    public void RemoveUser_ShouldNotRemoveDocumentStateWhenOtherUsersRemain()
    {
        awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");
        awareness.AddUser("doc-1", "s2", "u2", "Bob", "b@t.com");

        awareness.RemoveUser("s1");

        awareness.GetDocumentUserCount("doc-1").Should().Be(1);
        awareness.GetActiveDocumentIds().Should().Contain("doc-1");
    }

    [Fact]
    public void UpdateCursor_ShouldUpdateCursorPosition()
    {
        awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");

        var cursor = new CursorPosition { Index = 10, Length = 0 };
        var selection = new CursorPosition { Index = 10, Length = 5 };
        UserAwareness? result = awareness.UpdateCursor("s1", cursor, selection);

        result.Should().NotBeNull();
        result!.Cursor.Should().BeEquivalentTo(cursor);
        result.Selection.Should().BeEquivalentTo(selection);
    }

    [Fact]
    public void UpdateCursor_ShouldReturnNullForUnknownSocket()
    {
        UserAwareness? result = awareness.UpdateCursor("unknown", new CursorPosition { Index = 0, Length = 0 }, null);
        result.Should().BeNull();
    }

    [Fact]
    public void UpdateCursor_ShouldUpdateLastActiveTimestamp()
    {
        awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");

        long before = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        awareness.UpdateCursor("s1", new CursorPosition { Index = 5, Length = 0 }, null);
        List<UserAwareness> users = awareness.GetDocumentUsers("doc-1");

        users[0].LastActive.Should().BeGreaterThanOrEqualTo(before);
    }

    [Fact]
    public void SetTyping_ShouldUpdateTypingState()
    {
        awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");

        UserAwareness? result = awareness.SetTyping("s1", true);
        result.Should().NotBeNull();
        result!.IsTyping.Should().BeTrue();

        UserAwareness? result2 = awareness.SetTyping("s1", false);
        result2!.IsTyping.Should().BeFalse();
    }

    [Fact]
    public void SetTyping_ShouldReturnNullForUnknownSocket()
    {
        UserAwareness? result = awareness.SetTyping("unknown", true);
        result.Should().BeNull();
    }

    [Fact]
    public void GetDocumentUsers_ShouldReturnAllUsersInDocument()
    {
        awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");
        awareness.AddUser("doc-1", "s2", "u2", "Bob", "b@t.com");

        List<UserAwareness> users = awareness.GetDocumentUsers("doc-1");

        users.Should().HaveCount(2);
        users.Select(u => u.UserId).OrderBy(id => id).Should().BeEquivalentTo(new[] { "u1", "u2" });
    }

    [Fact]
    public void GetDocumentUsers_ShouldReturnEmptyForUnknownDocument()
    {
        List<UserAwareness> users = awareness.GetDocumentUsers("doc-unknown");
        users.Should().BeEmpty();
    }

    [Fact]
    public void GetUserDocument_ShouldReturnDocumentUserIsIn()
    {
        awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");

        awareness.GetUserDocument("s1").Should().Be("doc-1");
    }

    [Fact]
    public void GetUserDocument_ShouldReturnNullForUnknownSocket()
    {
        awareness.GetUserDocument("unknown").Should().BeNull();
    }

    [Fact]
    public void GetActiveDocumentIds_ShouldReturnAllActiveDocuments()
    {
        awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");
        awareness.AddUser("doc-2", "s2", "u2", "Bob", "b@t.com");
        awareness.AddUser("doc-3", "s3", "u3", "Charlie", "c@t.com");

        List<string> ids = awareness.GetActiveDocumentIds();
        ids.OrderBy(id => id).Should().BeEquivalentTo(new[] { "doc-1", "doc-2", "doc-3" });
    }

    [Fact]
    public void CleanupStaleUsers_ShouldRemoveUsersIdleBeyondThreshold()
    {
        awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");

        List<UserAwareness> users = awareness.GetDocumentUsers("doc-1");
        users[0].LastActive = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() - 400000;

        var removed = awareness.CleanupStaleUsers(300000);

        removed.Should().HaveCount(1);
        removed[0].UserId.Should().Be("u1");
        awareness.GetDocumentUserCount("doc-1").Should().Be(0);
    }

    [Fact]
    public void CleanupStaleUsers_ShouldNotRemoveActiveUsers()
    {
        awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");

        var removed = awareness.CleanupStaleUsers(300000);

        removed.Should().BeEmpty();
        awareness.GetDocumentUserCount("doc-1").Should().Be(1);
    }

    [Fact]
    public void RefreshActivity_ShouldReturnTrueAndUpdateTimestamp()
    {
        awareness.AddUser("doc-1", "s1", "u1", "Alice", "a@t.com");
        long before = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

        bool result = awareness.RefreshActivity("s1");

        result.Should().BeTrue();
        List<UserAwareness> users = awareness.GetDocumentUsers("doc-1");
        users[0].LastActive.Should().BeGreaterThanOrEqualTo(before);
    }

    [Fact]
    public void RefreshActivity_ShouldReturnFalseForUnknownSocket()
    {
        bool result = awareness.RefreshActivity("unknown");
        result.Should().BeFalse();
    }
}
