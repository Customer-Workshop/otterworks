using System.Security.Claims;
using FluentAssertions;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.CollabService.Hubs;
using OtterWorks.CollabService.Models;
using OtterWorks.CollabService.Services;

namespace CollabService.Tests.Unit;

public class CollaborationHubTests
{
    private readonly Mock<IDocumentStore> mockDocumentStore;
    private readonly Mock<IAwarenessService> mockAwareness;
    private readonly Mock<ILogger<CollaborationHub>> mockLogger;
    private readonly CollaborationHub hub;
    private readonly Mock<IHubCallerClients> mockClients;
    private readonly Mock<IGroupManager> mockGroups;
    private readonly Mock<HubCallerContext> mockContext;
    private readonly Mock<ISingleClientProxy> mockCallerProxy;
    private readonly Mock<ISingleClientProxy> mockGroupProxy;

    public CollaborationHubTests()
    {
        mockDocumentStore = new Mock<IDocumentStore>();
        mockAwareness = new Mock<IAwarenessService>();
        mockLogger = new Mock<ILogger<CollaborationHub>>();

        mockClients = new Mock<IHubCallerClients>();
        mockGroups = new Mock<IGroupManager>();
        mockContext = new Mock<HubCallerContext>();
        mockCallerProxy = new Mock<ISingleClientProxy>();
        mockGroupProxy = new Mock<ISingleClientProxy>();

        mockContext.Setup(c => c.ConnectionId).Returns("test-connection-id");
        var claims = new ClaimsPrincipal(new ClaimsIdentity(new[]
        {
            new Claim(ClaimTypes.NameIdentifier, "user-1"),
            new Claim(ClaimTypes.Email, "user1@test.com"),
            new Claim(ClaimTypes.Name, "Test User"),
            new Claim(ClaimTypes.Role, "user"),
        }, "test"));
        mockContext.Setup(c => c.User).Returns(claims);

        mockClients.Setup(c => c.Caller).Returns(mockCallerProxy.Object);
        mockClients.Setup(c => c.Group(It.IsAny<string>())).Returns(mockGroupProxy.Object);
        mockClients.Setup(c => c.GroupExcept(It.IsAny<string>(), It.IsAny<IReadOnlyList<string>>())).Returns(mockGroupProxy.Object);

        hub = new CollaborationHub(mockDocumentStore.Object, mockAwareness.Object, mockLogger.Object)
        {
            Clients = mockClients.Object,
            Groups = mockGroups.Object,
            Context = mockContext.Object,
        };
    }

    [Fact]
    public async Task JoinDocument_ShouldReturnSuccess()
    {
        mockAwareness.Setup(a => a.GetUserDocument("test-connection-id")).Returns((string?)null);
        mockAwareness.Setup(a => a.AddUser(
            "doc-join-test", "test-connection-id", "user-1", "Test User", "user1@test.com"))
            .Returns(new UserAwareness
            {
                UserId = "user-1",
                DisplayName = "Test User",
                Email = "user1@test.com",
                Color = "#FF6B6B",
            });
        mockDocumentStore.Setup(d => d.GetDocumentStateAsync("doc-join-test")).ReturnsAsync((byte[]?)null);
        mockAwareness.Setup(a => a.GetDocumentUsers("doc-join-test")).Returns(new List<UserAwareness>());

        object result = await hub.JoinDocument("doc-join-test");

        result.Should().BeEquivalentTo(new { success = true });
        mockGroups.Verify(g => g.AddToGroupAsync("test-connection-id", "doc:doc-join-test", default), Times.Once);
    }

    [Fact]
    public async Task JoinDocument_ShouldSyncDocumentState()
    {
        byte[] savedState = new byte[] { 1, 2, 3 };
        mockAwareness.Setup(a => a.GetUserDocument("test-connection-id")).Returns((string?)null);
        mockAwareness.Setup(a => a.AddUser(
            It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>()))
            .Returns(new UserAwareness { UserId = "user-1", Color = "#FF6B6B" });
        mockDocumentStore.Setup(d => d.GetDocumentStateAsync("doc-sync-test")).ReturnsAsync(savedState);
        mockAwareness.Setup(a => a.GetDocumentUsers(It.IsAny<string>())).Returns(new List<UserAwareness>());

        await hub.JoinDocument("doc-sync-test");

        mockCallerProxy.Verify(c => c.SendCoreAsync(
            "sync-document",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task JoinDocument_ShouldNotifyOtherUsers()
    {
        mockAwareness.Setup(a => a.GetUserDocument("test-connection-id")).Returns((string?)null);
        mockAwareness.Setup(a => a.AddUser(
            It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>()))
            .Returns(new UserAwareness { UserId = "user-1", DisplayName = "Test User", Color = "#FF6B6B" });
        mockDocumentStore.Setup(d => d.GetDocumentStateAsync(It.IsAny<string>())).ReturnsAsync((byte[]?)null);
        mockAwareness.Setup(a => a.GetDocumentUsers(It.IsAny<string>())).Returns(new List<UserAwareness>());

        await hub.JoinDocument("doc-notify-test");

        mockGroupProxy.Verify(c => c.SendCoreAsync(
            "user-joined",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task LeaveDocument_ShouldRemoveUserFromAwareness()
    {
        mockAwareness.Setup(a => a.RemoveUser("test-connection-id"))
            .Returns(("doc-leave-test", "user-1"));
        mockAwareness.Setup(a => a.GetDocumentUsers("doc-leave-test")).Returns(new List<UserAwareness>());

        await hub.LeaveDocument("doc-leave-test");

        mockAwareness.Verify(a => a.RemoveUser("test-connection-id"), Times.Once);
        mockGroups.Verify(g => g.RemoveFromGroupAsync("test-connection-id", "doc:doc-leave-test", default), Times.Once);
    }

    [Fact]
    public async Task LeaveDocument_ShouldNotifyOtherUsers()
    {
        mockAwareness.Setup(a => a.RemoveUser("test-connection-id"))
            .Returns(("doc-leave-test", "user-1"));
        mockAwareness.Setup(a => a.GetDocumentUsers("doc-leave-test")).Returns(new List<UserAwareness>());

        await hub.LeaveDocument("doc-leave-test");

        mockGroupProxy.Verify(c => c.SendCoreAsync(
            "user-left",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task DocumentUpdate_ShouldBroadcastToGroup()
    {
        string update = Convert.ToBase64String(new byte[] { 1, 2, 3 });

        await hub.DocumentUpdate("doc-update-test", update);

        mockGroupProxy.Verify(c => c.SendCoreAsync(
            "document-update",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task DocumentUpdate_ShouldPersistState()
    {
        byte[] stateBytes = new byte[] { 1, 2, 3 };
        string update = Convert.ToBase64String(stateBytes);

        await hub.DocumentUpdate("doc-persist-test", update);

        mockDocumentStore.Verify(d => d.SaveDocumentStateAsync(
            "doc-persist-test",
            It.Is<byte[]>(b => b.SequenceEqual(stateBytes)),
            "user-1"), Times.Once);
    }

    [Fact]
    public async Task DocumentUpdate_ShouldRefreshActivity()
    {
        string update = Convert.ToBase64String(new byte[] { 1, 2, 3 });

        await hub.DocumentUpdate("doc-activity-test", update);

        mockAwareness.Verify(a => a.RefreshActivity("test-connection-id"), Times.Once);
    }

    [Fact]
    public async Task CursorUpdate_ShouldBroadcastToGroup()
    {
        var cursor = new CursorPosition { Index = 42, Length = 0 };
        mockAwareness.Setup(a => a.UpdateCursor("test-connection-id", cursor, null))
            .Returns(new UserAwareness
            {
                UserId = "user-1",
                DisplayName = "Test User",
                Color = "#FF6B6B",
            });

        await hub.CursorUpdate("doc-cursor-test", cursor, null);

        mockGroupProxy.Verify(c => c.SendCoreAsync(
            "cursor-update",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task TypingIndicator_ShouldBroadcastToGroup()
    {
        mockAwareness.Setup(a => a.SetTyping("test-connection-id", true))
            .Returns(new UserAwareness
            {
                UserId = "user-1",
                DisplayName = "Test User",
            });

        await hub.TypingIndicator("doc-typing-test", true);

        mockGroupProxy.Verify(c => c.SendCoreAsync(
            "typing-indicator",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task OnDisconnectedAsync_ShouldRemoveUserAndNotify()
    {
        mockAwareness.Setup(a => a.RemoveUser("test-connection-id"))
            .Returns(("doc-disc-test", "user-1"));
        mockAwareness.Setup(a => a.GetDocumentUsers("doc-disc-test")).Returns(new List<UserAwareness>());

        await hub.OnDisconnectedAsync(null);

        mockAwareness.Verify(a => a.RemoveUser("test-connection-id"), Times.Once);
        mockGroupProxy.Verify(c => c.SendCoreAsync(
            "user-left",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task CommentAdd_ShouldBroadcastToGroup()
    {
        var comment = new CommentAnnotation
        {
            Id = "comment-1",
            ThreadId = "thread-1",
            Content = "Test comment",
            RangeStart = 0,
            RangeEnd = 10,
        };

        await hub.CommentAdd("doc-comment-test", comment);

        mockGroupProxy.Verify(c => c.SendCoreAsync(
            "comment-added",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task CommentUpdate_ShouldBroadcastToGroup()
    {
        await hub.CommentUpdate("doc-comment-test", "comment-1", "Updated content");

        mockGroupProxy.Verify(c => c.SendCoreAsync(
            "comment-updated",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task CommentDelete_ShouldBroadcastToGroup()
    {
        await hub.CommentDelete("doc-comment-test", "comment-1");

        mockGroupProxy.Verify(c => c.SendCoreAsync(
            "comment-deleted",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task RequestSnapshot_ShouldCreateAndBroadcast()
    {
        byte[] state = new byte[] { 1, 2, 3 };
        mockDocumentStore.Setup(d => d.GetDocumentStateAsync("doc-snap-test")).ReturnsAsync(state);
        mockDocumentStore.Setup(d => d.CreateSnapshotAsync("doc-snap-test", state, "user-1", "v1"))
            .ReturnsAsync(new DocumentSnapshot
            {
                Id = "snap-1",
                DocumentId = "doc-snap-test",
                CreatedBy = "user-1",
                Label = "v1",
            });

        await hub.RequestSnapshot("doc-snap-test", "v1");

        mockGroupProxy.Verify(c => c.SendCoreAsync(
            "snapshot-created",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task RequestSnapshot_ShouldSendErrorWhenDocumentNotFound()
    {
        mockDocumentStore.Setup(d => d.GetDocumentStateAsync("doc-missing")).ReturnsAsync((byte[]?)null);

        await hub.RequestSnapshot("doc-missing", null);

        mockCallerProxy.Verify(c => c.SendCoreAsync(
            "snapshot-error",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task RequestHistory_ShouldReturnSnapshots()
    {
        var snapshots = new List<DocumentSnapshot>
        {
            new() { Id = "snap-1", DocumentId = "doc-hist-test" },
            new() { Id = "snap-2", DocumentId = "doc-hist-test" },
        };
        mockDocumentStore.Setup(d => d.GetSnapshotsAsync("doc-hist-test", 20)).ReturnsAsync(snapshots);

        await hub.RequestHistory("doc-hist-test", null);

        mockCallerProxy.Verify(c => c.SendCoreAsync(
            "document-history",
            It.Is<object?[]>(args => args.Length == 1),
            default), Times.Once);
    }

    [Fact]
    public async Task JoinDocument_ShouldSwitchDocumentsWhenAlreadyInAnother()
    {
        mockAwareness.Setup(a => a.GetUserDocument("test-connection-id")).Returns("old-doc");
        mockAwareness.Setup(a => a.RemoveUser("test-connection-id"))
            .Returns(("old-doc", "user-1"));
        mockAwareness.Setup(a => a.AddUser(
            It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>(), It.IsAny<string>()))
            .Returns(new UserAwareness { UserId = "user-1", Color = "#FF6B6B" });
        mockDocumentStore.Setup(d => d.GetDocumentStateAsync(It.IsAny<string>())).ReturnsAsync((byte[]?)null);
        mockAwareness.Setup(a => a.GetDocumentUsers(It.IsAny<string>())).Returns(new List<UserAwareness>());

        object result = await hub.JoinDocument("new-doc");

        result.Should().BeEquivalentTo(new { success = true });
        mockGroups.Verify(g => g.RemoveFromGroupAsync("test-connection-id", "doc:old-doc", default), Times.Once);
        mockAwareness.Verify(a => a.RemoveUser("test-connection-id"), Times.Once);
    }
}
