using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using OtterWorks.CollabService.Models;
using OtterWorks.CollabService.Services;

namespace OtterWorks.CollabService.Hubs;

[Authorize]
public class CollaborationHub : Hub
{
    private readonly IDocumentStore documentStore;
    private readonly IAwarenessService awareness;
    private readonly ILogger<CollaborationHub> logger;

    public CollaborationHub(
        IDocumentStore documentStore,
        IAwarenessService awareness,
        ILogger<CollaborationHub> logger)
    {
        this.documentStore = documentStore;
        this.awareness = awareness;
        this.logger = logger;
    }

    public override async Task OnConnectedAsync()
    {
        logger.LogInformation("Client connected: {ConnectionId}", Context.ConnectionId);
        await base.OnConnectedAsync();
    }

    public override async Task OnDisconnectedAsync(Exception? exception)
    {
        logger.LogInformation("Client disconnected: {ConnectionId} {Reason}", Context.ConnectionId, exception?.Message ?? "clean");

        (string DocumentId, string UserId)? mapping = awareness.RemoveUser(Context.ConnectionId);
        if (mapping.HasValue)
        {
            string room = $"doc:{mapping.Value.DocumentId}";
            await Clients.Group(room).SendAsync(
                "user-left",
                new { socketId = Context.ConnectionId, userId = mapping.Value.UserId });

            await BroadcastPresenceUpdateAsync(mapping.Value.DocumentId);
        }

        await base.OnDisconnectedAsync(exception);
    }

    public async Task<object> JoinDocument(string documentId)
    {
        AuthenticatedUser user = GetAuthenticatedUser();
        string room = $"doc:{documentId}";

        try
        {
            string? oldDocId = awareness.GetUserDocument(Context.ConnectionId);
            if (oldDocId is not null && oldDocId != documentId)
            {
                string oldRoom = $"doc:{oldDocId}";
                await Groups.RemoveFromGroupAsync(Context.ConnectionId, oldRoom);
                awareness.RemoveUser(Context.ConnectionId);
                await Clients.Group(oldRoom).SendAsync(
                    "user-left",
                    new { socketId = Context.ConnectionId, userId = user.UserId });
                await BroadcastPresenceUpdateAsync(oldDocId);

                logger.LogInformation("User switched documents: {OldDoc} -> {NewDoc} ({UserId})", oldDocId, documentId, user.UserId);
            }

            await Groups.AddToGroupAsync(Context.ConnectionId, room);
            logger.LogInformation("User joined document: {DocumentId} {UserId} {ConnectionId}", documentId, user.UserId, Context.ConnectionId);

            UserAwareness userAwareness = awareness.AddUser(
                documentId,
                Context.ConnectionId,
                user.UserId,
                user.DisplayName,
                user.Email);

            byte[]? savedState = await documentStore.GetDocumentStateAsync(documentId);
            string stateBase64 = savedState is not null ? Convert.ToBase64String(savedState) : Convert.ToBase64String(Array.Empty<byte>());

            await Clients.Caller.SendAsync("sync-document", new { documentId, state = stateBase64 });

            await Clients.GroupExcept(room, Context.ConnectionId).SendAsync(
                "user-joined",
                new
                {
                    userId = user.UserId,
                    displayName = user.DisplayName,
                    color = userAwareness.Color,
                    socketId = Context.ConnectionId,
                });

            await BroadcastPresenceUpdateAsync(documentId);

            return new { success = true };
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Join document failed: {DocumentId} {ConnectionId}", documentId, Context.ConnectionId);
            await Groups.RemoveFromGroupAsync(Context.ConnectionId, room);
            return new { success = false, error = "Failed to join document" };
        }
    }

    public async Task LeaveDocument(string documentId)
    {
        (string DocumentId, string UserId)? mapping = awareness.RemoveUser(Context.ConnectionId);
        string trackedDocId = mapping?.DocumentId ?? documentId;
        string room = $"doc:{trackedDocId}";

        await Groups.RemoveFromGroupAsync(Context.ConnectionId, room);

        if (mapping.HasValue)
        {
            await Clients.Group(room).SendAsync(
                "user-left",
                new { socketId = Context.ConnectionId, userId = mapping.Value.UserId });
            await BroadcastPresenceUpdateAsync(trackedDocId);
        }

        logger.LogInformation("User left document: {DocumentId} {ConnectionId}", trackedDocId, Context.ConnectionId);
    }

    public async Task DocumentUpdate(string documentId, string update)
    {
        string room = $"doc:{documentId}";
        AuthenticatedUser user = GetAuthenticatedUser();

        awareness.RefreshActivity(Context.ConnectionId);

        await Clients.GroupExcept(room, Context.ConnectionId).SendAsync(
            "document-update",
            new { documentId, update });

        try
        {
            byte[] stateBytes = Convert.FromBase64String(update);
            await documentStore.SaveDocumentStateAsync(documentId, stateBytes, user.UserId);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Document persist failed: {DocumentId} {ConnectionId}", documentId, Context.ConnectionId);
        }
    }

    public async Task CursorUpdate(string documentId, CursorPosition? cursor, CursorPosition? selection)
    {
        UserAwareness? updatedAwareness = awareness.UpdateCursor(Context.ConnectionId, cursor, selection);

        if (updatedAwareness is not null)
        {
            string room = $"doc:{documentId}";
            await Clients.GroupExcept(room, Context.ConnectionId).SendAsync(
                "cursor-update",
                new
                {
                    socketId = Context.ConnectionId,
                    userId = updatedAwareness.UserId,
                    displayName = updatedAwareness.DisplayName,
                    color = updatedAwareness.Color,
                    cursor,
                    selection,
                });
        }
    }

    public async Task TypingIndicator(string documentId, bool isTyping)
    {
        UserAwareness? updated = awareness.SetTyping(Context.ConnectionId, isTyping);

        if (updated is not null)
        {
            string room = $"doc:{documentId}";
            await Clients.GroupExcept(room, Context.ConnectionId).SendAsync(
                "typing-indicator",
                new
                {
                    socketId = Context.ConnectionId,
                    userId = updated.UserId,
                    displayName = updated.DisplayName,
                    isTyping,
                });
        }
    }

    public async Task CommentAdd(string documentId, CommentAnnotation comment)
    {
        AuthenticatedUser user = GetAuthenticatedUser();
        string room = $"doc:{documentId}";

        var fullComment = new CommentAnnotation
        {
            Id = comment.Id,
            DocumentId = documentId,
            ThreadId = comment.ThreadId,
            Content = comment.Content,
            Author = new CommentAuthor { UserId = user.UserId, DisplayName = user.DisplayName },
            RangeStart = comment.RangeStart,
            RangeEnd = comment.RangeEnd,
            CreatedAt = DateTime.UtcNow.ToString("o"),
            ParentId = comment.ParentId,
        };

        await Clients.Group(room).SendAsync("comment-added", fullComment);
    }

    public async Task CommentUpdate(string documentId, string commentId, string content)
    {
        AuthenticatedUser user = GetAuthenticatedUser();
        string room = $"doc:{documentId}";

        await Clients.GroupExcept(room, Context.ConnectionId).SendAsync(
            "comment-updated",
            new
            {
                commentId,
                content,
                updatedBy = new { userId = user.UserId, displayName = user.DisplayName },
                updatedAt = DateTime.UtcNow.ToString("o"),
            });
    }

    public async Task CommentDelete(string documentId, string commentId)
    {
        AuthenticatedUser user = GetAuthenticatedUser();
        string room = $"doc:{documentId}";

        await Clients.GroupExcept(room, Context.ConnectionId).SendAsync(
            "comment-deleted",
            new { commentId, deletedBy = user.UserId });
    }

    public async Task RequestSnapshot(string documentId, string? label)
    {
        AuthenticatedUser user = GetAuthenticatedUser();

        try
        {
            byte[]? currentState = await documentStore.GetDocumentStateAsync(documentId);
            if (currentState is null)
            {
                await Clients.Caller.SendAsync("snapshot-error", new { documentId, error = "Document not found" });
                return;
            }

            DocumentSnapshot snapshot = await documentStore.CreateSnapshotAsync(documentId, currentState, user.UserId, label);

            string room = $"doc:{documentId}";
            await Clients.Group(room).SendAsync("snapshot-created", snapshot);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Create snapshot failed: {DocumentId}", documentId);
            await Clients.Caller.SendAsync("snapshot-error", new { documentId, error = "Failed to create snapshot" });
        }
    }

    public async Task RequestHistory(string documentId, int? limit)
    {
        try
        {
            List<DocumentSnapshot> snapshots = await documentStore.GetSnapshotsAsync(documentId, limit ?? 20);
            await Clients.Caller.SendAsync("document-history", new { documentId, snapshots });
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Get history failed: {DocumentId}", documentId);
            await Clients.Caller.SendAsync("history-error", new { documentId, error = "Failed to retrieve history" });
        }
    }

    private AuthenticatedUser GetAuthenticatedUser()
    {
        ClaimsPrincipal? principal = Context.User;
        return new AuthenticatedUser
        {
            UserId = principal?.FindFirst(ClaimTypes.NameIdentifier)?.Value
                     ?? principal?.FindFirst("sub")?.Value
                     ?? $"anon-{Context.ConnectionId}",
            Email = principal?.FindFirst(ClaimTypes.Email)?.Value
                    ?? principal?.FindFirst("email")?.Value
                    ?? string.Empty,
            DisplayName = principal?.FindFirst(ClaimTypes.Name)?.Value
                          ?? principal?.FindFirst("name")?.Value
                          ?? principal?.FindFirst("display_name")?.Value
                          ?? "Anonymous",
            Roles = principal?.FindAll(ClaimTypes.Role).Select(c => c.Value).ToArray() ?? [],
        };
    }

    private async Task BroadcastPresenceUpdateAsync(string documentId)
    {
        List<UserAwareness> users = awareness.GetDocumentUsers(documentId);
        string room = $"doc:{documentId}";
        await Clients.Group(room).SendAsync("presence-update", new PresenceInfo
        {
            DocumentId = documentId,
            Users = users,
            Count = users.Count,
        });
    }
}
