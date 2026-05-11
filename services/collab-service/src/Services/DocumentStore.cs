using System.Text.Json;
using OtterWorks.CollabService.Config;
using OtterWorks.CollabService.Models;

namespace OtterWorks.CollabService.Services;

public class DocumentStore : IDocumentStore
{
    private const string DocStateKey = "doc:state:";
    private const string DocSnapshotsKey = "doc:snapshots:";
    private const string DocMetaKey = "doc:meta:";

    private readonly IRedisAdapter redis;
    private readonly ILogger<DocumentStore> logger;
    private readonly int documentTtl;
    private readonly int snapshotTtl;
    private readonly int maxSnapshots;

    public DocumentStore(
        IRedisAdapter redis,
        ILogger<DocumentStore> logger,
        PersistenceSettings settings)
    {
        this.redis = redis;
        this.logger = logger;
        documentTtl = settings.DocumentTtlSeconds;
        snapshotTtl = settings.SnapshotTtlSeconds;
        maxSnapshots = settings.MaxSnapshotsPerDocument;
    }

    public async Task<byte[]?> GetDocumentStateAsync(string documentId)
    {
        return await redis.GetAsync($"{DocStateKey}{documentId}");
    }

    public async Task SaveDocumentStateAsync(string documentId, byte[] state, string? userId = null)
    {
        await redis.SetAsync($"{DocStateKey}{documentId}", state, documentTtl);

        string now = DateTime.UtcNow.ToString("o");
        string metaKey = $"{DocMetaKey}{documentId}";

        await redis.HashSetAsync(metaKey, "documentId", documentId);
        await redis.HashSetAsync(metaKey, "lastModifiedAt", now);
        await redis.HashSetAsync(metaKey, "lastModifiedBy", userId ?? "system");
        await redis.HashIncrementAsync(metaKey, "version", 1);

        string? createdAt = await redis.HashGetAsync(metaKey, "createdAt");
        if (createdAt is null)
        {
            await redis.HashSetAsync(metaKey, "createdAt", now);
        }

        await redis.ExpireAsync(metaKey, documentTtl);

        logger.LogDebug("Document state saved: {DocumentId}", documentId);
    }

    public async Task DeleteDocumentStateAsync(string documentId)
    {
        await redis.DeleteAsync($"{DocStateKey}{documentId}");
        await redis.DeleteAsync($"{DocMetaKey}{documentId}");
        await redis.DeleteAsync($"{DocSnapshotsKey}{documentId}");
        logger.LogInformation("Document state deleted: {DocumentId}", documentId);
    }

    public async Task<DocumentMeta?> GetDocumentMetaAsync(string documentId)
    {
        Dictionary<string, string> data = await redis.HashGetAllAsync($"{DocMetaKey}{documentId}");
        if (data.Count == 0 || !data.TryGetValue("documentId", out string? docId))
        {
            return null;
        }

        return new DocumentMeta
        {
            DocumentId = docId,
            CreatedAt = data.GetValueOrDefault("createdAt", string.Empty),
            LastModifiedAt = data.GetValueOrDefault("lastModifiedAt", string.Empty),
            LastModifiedBy = data.GetValueOrDefault("lastModifiedBy", string.Empty),
            Version = int.TryParse(data.GetValueOrDefault("version", "0"), out int v) ? v : 0,
        };
    }

    public async Task<DocumentSnapshot> CreateSnapshotAsync(string documentId, byte[] state, string createdBy, string? label = null)
    {
        var snapshot = new DocumentSnapshot
        {
            Id = Guid.NewGuid().ToString(),
            DocumentId = documentId,
            State = Convert.ToBase64String(state),
            CreatedAt = DateTime.UtcNow.ToString("o"),
            CreatedBy = createdBy,
            Label = label,
        };

        string key = $"{DocSnapshotsKey}{documentId}";
        await redis.ListPushAsync(key, JsonSerializer.Serialize(snapshot));

        long count = await redis.ListLengthAsync(key);
        if (count > maxSnapshots)
        {
            await redis.ListTrimAsync(key, 0, maxSnapshots - 1);
        }

        await redis.ExpireAsync(key, snapshotTtl);

        logger.LogInformation("Snapshot created: {DocumentId} by {CreatedBy}", documentId, createdBy);

        return snapshot;
    }

    public async Task<List<DocumentSnapshot>> GetSnapshotsAsync(string documentId, int limit = 20)
    {
        string key = $"{DocSnapshotsKey}{documentId}";
        string[] raw = await redis.ListRangeAsync(key, 0, limit - 1);
        return raw
            .Select(item => JsonSerializer.Deserialize<DocumentSnapshot>(item))
            .Where(s => s is not null)
            .Cast<DocumentSnapshot>()
            .ToList();
    }

    public async Task<byte[]?> GetSnapshotStateAsync(string documentId, string snapshotId)
    {
        List<DocumentSnapshot> snapshots = await GetSnapshotsAsync(documentId, maxSnapshots);
        DocumentSnapshot? snapshot = snapshots.Find(s => s.Id == snapshotId);
        if (snapshot is null)
        {
            return null;
        }

        return Convert.FromBase64String(snapshot.State);
    }
}
