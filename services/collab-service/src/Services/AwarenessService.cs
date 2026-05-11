using OtterWorks.CollabService.Models;

namespace OtterWorks.CollabService.Services;

public class AwarenessService : IAwarenessService
{
    private static readonly string[] UserColors =
    [
        "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
        "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
        "#F0B27A", "#82E0AA", "#F1948A", "#85929E", "#73C6B6",
        "#E59866", "#AED6F1", "#D7BDE2", "#A3E4D7", "#FAD7A0",
    ];

    private readonly Dictionary<string, AwarenessState> states = new();
    private readonly Dictionary<string, (string DocumentId, string UserId)> connectionToDocument = new();
    private readonly ILogger<AwarenessService> logger;
    private readonly object syncLock = new();
    private int colorIndex;

    public AwarenessService(ILogger<AwarenessService> logger)
    {
        this.logger = logger;
    }

    public UserAwareness AddUser(string documentId, string connectionId, string userId, string displayName, string email)
    {
        lock (syncLock)
        {
            if (!states.TryGetValue(documentId, out AwarenessState? state))
            {
                state = new AwarenessState { DocumentId = documentId };
                states[documentId] = state;
            }

            var awareness = new UserAwareness
            {
                UserId = userId,
                DisplayName = displayName,
                Email = email,
                Color = AssignColor(),
                Cursor = null,
                Selection = null,
                IsTyping = false,
                LastActive = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
            };

            if (connectionToDocument.TryGetValue(connectionId, out (string DocumentId, string UserId) oldMapping)
                && oldMapping.DocumentId != documentId)
            {
                if (states.TryGetValue(oldMapping.DocumentId, out AwarenessState? oldState))
                {
                    oldState.Users.Remove(connectionId);
                    if (oldState.Users.Count == 0)
                    {
                        states.Remove(oldMapping.DocumentId);
                    }
                }

                logger.LogDebug(
                    "Awareness socket moved: {OldDocId} -> {NewDocId} ({ConnectionId})",
                    oldMapping.DocumentId,
                    documentId,
                    connectionId);
            }

            state.Users[connectionId] = awareness;
            connectionToDocument[connectionId] = (documentId, userId);

            logger.LogDebug("Awareness user added: {DocumentId} {ConnectionId} {UserId}", documentId, connectionId, userId);

            return awareness;
        }
    }

    public (string DocumentId, string UserId)? RemoveUser(string connectionId)
    {
        lock (syncLock)
        {
            if (!connectionToDocument.TryGetValue(connectionId, out (string DocumentId, string UserId) mapping))
            {
                return null;
            }

            if (states.TryGetValue(mapping.DocumentId, out AwarenessState? state))
            {
                state.Users.Remove(connectionId);
                if (state.Users.Count == 0)
                {
                    states.Remove(mapping.DocumentId);
                }
            }

            connectionToDocument.Remove(connectionId);

            logger.LogDebug("Awareness user removed: {DocumentId} {ConnectionId} {UserId}", mapping.DocumentId, connectionId, mapping.UserId);

            return mapping;
        }
    }

    public UserAwareness? UpdateCursor(string connectionId, CursorPosition? cursor, CursorPosition? selection)
    {
        lock (syncLock)
        {
            if (!connectionToDocument.TryGetValue(connectionId, out (string DocumentId, string UserId) mapping))
            {
                return null;
            }

            if (!states.TryGetValue(mapping.DocumentId, out AwarenessState? state))
            {
                return null;
            }

            if (!state.Users.TryGetValue(connectionId, out UserAwareness? awareness))
            {
                return null;
            }

            awareness.Cursor = cursor;
            awareness.Selection = selection;
            awareness.LastActive = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

            return awareness;
        }
    }

    public UserAwareness? SetTyping(string connectionId, bool isTyping)
    {
        lock (syncLock)
        {
            if (!connectionToDocument.TryGetValue(connectionId, out (string DocumentId, string UserId) mapping))
            {
                return null;
            }

            if (!states.TryGetValue(mapping.DocumentId, out AwarenessState? state))
            {
                return null;
            }

            if (!state.Users.TryGetValue(connectionId, out UserAwareness? awareness))
            {
                return null;
            }

            awareness.IsTyping = isTyping;
            awareness.LastActive = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

            return awareness;
        }
    }

    public List<UserAwareness> GetDocumentUsers(string documentId)
    {
        lock (syncLock)
        {
            if (!states.TryGetValue(documentId, out AwarenessState? state))
            {
                return [];
            }

            return state.Users.Values.ToList();
        }
    }

    public int GetDocumentUserCount(string documentId)
    {
        lock (syncLock)
        {
            if (!states.TryGetValue(documentId, out AwarenessState? state))
            {
                return 0;
            }

            return state.Users.Count;
        }
    }

    public string? GetUserDocument(string connectionId)
    {
        lock (syncLock)
        {
            return connectionToDocument.TryGetValue(connectionId, out (string DocumentId, string UserId) mapping)
                ? mapping.DocumentId
                : null;
        }
    }

    public List<string> GetActiveDocumentIds()
    {
        lock (syncLock)
        {
            return states.Keys.ToList();
        }
    }

    public bool RefreshActivity(string connectionId)
    {
        lock (syncLock)
        {
            if (!connectionToDocument.TryGetValue(connectionId, out (string DocumentId, string UserId) mapping))
            {
                return false;
            }

            if (!states.TryGetValue(mapping.DocumentId, out AwarenessState? state))
            {
                return false;
            }

            if (!state.Users.TryGetValue(connectionId, out UserAwareness? awareness))
            {
                return false;
            }

            awareness.LastActive = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            return true;
        }
    }

    public List<(string ConnectionId, string DocumentId, string UserId)> CleanupStaleUsers(long maxIdleMs)
    {
        lock (syncLock)
        {
            var removed = new List<(string ConnectionId, string DocumentId, string UserId)>();
            long now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            var emptyDocuments = new List<string>();

            foreach ((string documentId, AwarenessState state) in states)
            {
                var staleConnections = new List<string>();

                foreach ((string connId, UserAwareness awareness) in state.Users)
                {
                    if (now - awareness.LastActive > maxIdleMs)
                    {
                        staleConnections.Add(connId);
                        removed.Add((connId, documentId, awareness.UserId));
                    }
                }

                foreach (string connId in staleConnections)
                {
                    state.Users.Remove(connId);
                    connectionToDocument.Remove(connId);
                }

                if (state.Users.Count == 0)
                {
                    emptyDocuments.Add(documentId);
                }
            }

            foreach (string docId in emptyDocuments)
            {
                states.Remove(docId);
            }

            if (removed.Count > 0)
            {
                logger.LogInformation("Awareness stale users cleaned: {Count}", removed.Count);
            }

            return removed;
        }
    }

    private string AssignColor()
    {
        string color = UserColors[colorIndex % UserColors.Length];
        colorIndex++;
        return color;
    }

    private sealed class AwarenessState
    {
        public string DocumentId { get; set; } = string.Empty;

        public Dictionary<string, UserAwareness> Users { get; } = new();
    }
}
