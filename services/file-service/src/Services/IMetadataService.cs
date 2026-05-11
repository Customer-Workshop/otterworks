using OtterWorks.FileService.Models;

namespace OtterWorks.FileService.Services;

public interface IMetadataService
{
    Task PutFileAsync(FileMetadata file);

    Task<FileMetadata?> GetFileAsync(Guid fileId);

    Task DeleteFileAsync(Guid fileId);

    Task<FileMetadata?> TrashFileAsync(Guid fileId);

    Task<FileMetadata?> RestoreFileAsync(Guid fileId);

    Task<FileMetadata?> RenameFileAsync(Guid fileId, string name);

    Task<FileMetadata?> MoveFileAsync(Guid fileId, Guid? folderId);

    Task<List<FileMetadata>> ListFilesAsync(Guid? folderId, Guid? ownerId, bool includeTrashed);

    Task<List<FileMetadata>> ListTrashedAsync(Guid? ownerId);

    Task PutFolderAsync(Folder folder);

    Task<Folder?> GetFolderAsync(Guid folderId);

    Task<Folder?> UpdateFolderAsync(Guid folderId, string? name, Guid? parentId);

    Task DeleteFolderAsync(Guid folderId);

    Task<List<Folder>> ListFoldersAsync(Guid? parentId, Guid? ownerId);

    Task PutVersionAsync(FileVersion version);

    Task<List<FileVersion>> ListVersionsAsync(Guid fileId);

    Task PutShareAsync(FileShare share);

    Task<FileShare?> FindExistingShareAsync(Guid fileId, Guid sharedWith);

    Task<List<FileShare>> ListSharesForUserAsync(Guid userId);

    Task<List<FileShare>> ListSharesByOwnerAsync(Guid ownerId);

    Task DeleteShareAsync(Guid shareId);

    Task<List<FileShare>> ListSharesAsync(Guid fileId);
}
