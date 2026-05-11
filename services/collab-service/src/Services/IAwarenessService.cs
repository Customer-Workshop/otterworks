using OtterWorks.CollabService.Models;

namespace OtterWorks.CollabService.Services;

public interface IAwarenessService
{
    UserAwareness AddUser(string documentId, string connectionId, string userId, string displayName, string email);

    (string DocumentId, string UserId)? RemoveUser(string connectionId);

    UserAwareness? UpdateCursor(string connectionId, CursorPosition? cursor, CursorPosition? selection);

    UserAwareness? SetTyping(string connectionId, bool isTyping);

    List<UserAwareness> GetDocumentUsers(string documentId);

    int GetDocumentUserCount(string documentId);

    string? GetUserDocument(string connectionId);

    List<string> GetActiveDocumentIds();

    bool RefreshActivity(string connectionId);

    List<(string ConnectionId, string DocumentId, string UserId)> CleanupStaleUsers(long maxIdleMs);
}
