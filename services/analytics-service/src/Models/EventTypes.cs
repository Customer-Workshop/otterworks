namespace OtterWorks.AnalyticsService.Models;

public static class EventTypes
{
    public const string DocumentCreated = "document.created";
    public const string DocumentViewed = "document.viewed";
    public const string DocumentEdited = "document.edited";
    public const string DocumentShared = "document.shared";
    public const string DocumentDeleted = "document.deleted";
    public const string FileUploaded = "file.uploaded";
    public const string FileDownloaded = "file.downloaded";
    public const string FileDeleted = "file.deleted";
    public const string FileShared = "file.shared";
    public const string UserLoggedIn = "user.logged_in";
    public const string UserLoggedOut = "user.logged_out";
    public const string CollabSessionStarted = "collab.session_started";
    public const string CollabSessionEnded = "collab.session_ended";
    public const string StorageAllocated = "storage.allocated";
    public const string StorageReleased = "storage.released";

    public static readonly HashSet<string> All = new()
    {
        DocumentCreated, DocumentViewed, DocumentEdited, DocumentShared, DocumentDeleted,
        FileUploaded, FileDownloaded, FileDeleted, FileShared,
        UserLoggedIn, UserLoggedOut,
        CollabSessionStarted, CollabSessionEnded,
        StorageAllocated, StorageReleased,
    };
}
