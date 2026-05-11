using OtterWorks.CollabService.Models;

namespace OtterWorks.CollabService.Services;

public interface IDocumentStore
{
    Task<byte[]?> GetDocumentStateAsync(string documentId);

    Task SaveDocumentStateAsync(string documentId, byte[] state, string? userId = null);

    Task DeleteDocumentStateAsync(string documentId);

    Task<DocumentMeta?> GetDocumentMetaAsync(string documentId);

    Task<DocumentSnapshot> CreateSnapshotAsync(string documentId, byte[] state, string createdBy, string? label = null);

    Task<List<DocumentSnapshot>> GetSnapshotsAsync(string documentId, int limit = 20);

    Task<byte[]?> GetSnapshotStateAsync(string documentId, string snapshotId);
}
