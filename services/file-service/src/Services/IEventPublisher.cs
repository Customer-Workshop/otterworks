namespace OtterWorks.FileService.Services;

public interface IEventPublisher
{
    Task FileUploadedAsync(Guid fileId, Guid ownerId, Guid? folderId, string name, string mimeType, long sizeBytes);

    Task FileDeletedAsync(Guid fileId, Guid ownerId);

    Task FileSharedAsync(Guid fileId, Guid ownerId, Guid sharedWith);

    Task FileTrashedAsync(Guid fileId, Guid ownerId);

    Task FileRestoredAsync(Guid fileId, Guid ownerId, Guid? folderId, string name, string mimeType, long sizeBytes);

    Task FileUpdatedAsync(Guid fileId, Guid ownerId, Guid? folderId, string name, string mimeType, long sizeBytes);

    Task FileMovedAsync(Guid fileId, Guid ownerId, Guid? folderId);
}
