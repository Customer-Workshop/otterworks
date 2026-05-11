using System.Text.Json;
using FluentAssertions;
using Microsoft.Extensions.Logging;
using Moq;
using OtterWorks.CollabService.Config;
using OtterWorks.CollabService.Models;
using OtterWorks.CollabService.Services;

namespace CollabService.Tests.Unit;

public class DocumentStoreTests
{
    private readonly Mock<IRedisAdapter> mockRedis;
    private readonly DocumentStore store;

    public DocumentStoreTests()
    {
        mockRedis = new Mock<IRedisAdapter>();
        var logger = new Mock<ILogger<DocumentStore>>();
        var settings = new PersistenceSettings
        {
            DocumentTtlSeconds = 86400,
            SnapshotTtlSeconds = 604800,
            MaxSnapshotsPerDocument = 50,
        };
        store = new DocumentStore(mockRedis.Object, logger.Object, settings);
    }

    [Fact]
    public async Task GetDocumentState_ShouldReturnNullWhenNoDocumentExists()
    {
        mockRedis.Setup(r => r.GetAsync(It.IsAny<string>())).ReturnsAsync((byte[]?)null);

        byte[]? result = await store.GetDocumentStateAsync("doc-123");

        result.Should().BeNull();
        mockRedis.Verify(r => r.GetAsync("doc:state:doc-123"), Times.Once);
    }

    [Fact]
    public async Task GetDocumentState_ShouldReturnByteArrayWhenDocumentExists()
    {
        byte[] state = new byte[] { 1, 2, 3, 4, 5 };
        mockRedis.Setup(r => r.GetAsync("doc:state:doc-123")).ReturnsAsync(state);

        byte[]? result = await store.GetDocumentStateAsync("doc-123");

        result.Should().NotBeNull();
        result.Should().BeEquivalentTo(state);
    }

    [Fact]
    public async Task SaveDocumentState_ShouldSaveStateWithTtl()
    {
        byte[] state = new byte[] { 1, 2, 3 };
        mockRedis.Setup(r => r.HashGetAsync(It.IsAny<string>(), "createdAt")).ReturnsAsync((string?)null);
        mockRedis.Setup(r => r.HashIncrementAsync(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<long>())).ReturnsAsync(1);

        await store.SaveDocumentStateAsync("doc-456", state, "user-1");

        mockRedis.Verify(r => r.SetAsync("doc:state:doc-456", state, 86400), Times.Once);
    }

    [Fact]
    public async Task SaveDocumentState_ShouldUpdateMetadata()
    {
        byte[] state = new byte[] { 1, 2, 3 };
        mockRedis.Setup(r => r.HashGetAsync("doc:meta:doc-456", "createdAt")).ReturnsAsync("2024-01-01T00:00:00Z");
        mockRedis.Setup(r => r.HashIncrementAsync("doc:meta:doc-456", "version", 1)).ReturnsAsync(6);

        await store.SaveDocumentStateAsync("doc-456", state, "user-1");

        mockRedis.Verify(r => r.HashIncrementAsync("doc:meta:doc-456", "version", 1), Times.Once);
        mockRedis.Verify(r => r.HashSetAsync("doc:meta:doc-456", "lastModifiedBy", "user-1"), Times.Once);
    }

    [Fact]
    public async Task SaveDocumentState_ShouldSetCreatedAtOnFirstSave()
    {
        byte[] state = new byte[] { 1, 2, 3 };
        mockRedis.Setup(r => r.HashGetAsync("doc:meta:doc-new", "createdAt")).ReturnsAsync((string?)null);
        mockRedis.Setup(r => r.HashIncrementAsync(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<long>())).ReturnsAsync(1);

        await store.SaveDocumentStateAsync("doc-new", state);

        mockRedis.Verify(r => r.HashSetAsync("doc:meta:doc-new", "createdAt", It.IsAny<string>()), Times.Once);
    }

    [Fact]
    public async Task SaveDocumentState_ShouldDefaultUserIdToSystem()
    {
        byte[] state = new byte[] { 1, 2, 3 };
        mockRedis.Setup(r => r.HashGetAsync(It.IsAny<string>(), "createdAt")).ReturnsAsync((string?)null);
        mockRedis.Setup(r => r.HashIncrementAsync(It.IsAny<string>(), It.IsAny<string>(), It.IsAny<long>())).ReturnsAsync(1);

        await store.SaveDocumentStateAsync("doc-456", state);

        mockRedis.Verify(r => r.HashSetAsync("doc:meta:doc-456", "lastModifiedBy", "system"), Times.Once);
    }

    [Fact]
    public async Task DeleteDocumentState_ShouldDeleteAllKeysForDocument()
    {
        await store.DeleteDocumentStateAsync("doc-789");

        mockRedis.Verify(r => r.DeleteAsync("doc:state:doc-789"), Times.Once);
        mockRedis.Verify(r => r.DeleteAsync("doc:meta:doc-789"), Times.Once);
        mockRedis.Verify(r => r.DeleteAsync("doc:snapshots:doc-789"), Times.Once);
    }

    [Fact]
    public async Task GetDocumentMeta_ShouldReturnNullWhenNoMetadataExists()
    {
        mockRedis.Setup(r => r.HashGetAllAsync(It.IsAny<string>())).ReturnsAsync(new Dictionary<string, string>());

        DocumentMeta? result = await store.GetDocumentMetaAsync("doc-missing");

        result.Should().BeNull();
    }

    [Fact]
    public async Task GetDocumentMeta_ShouldReturnParsedMetadata()
    {
        mockRedis.Setup(r => r.HashGetAllAsync("doc:meta:doc-123")).ReturnsAsync(new Dictionary<string, string>
        {
            ["documentId"] = "doc-123",
            ["createdAt"] = "2024-01-01T00:00:00Z",
            ["lastModifiedAt"] = "2024-01-02T12:00:00Z",
            ["lastModifiedBy"] = "user-1",
            ["version"] = "42",
        });

        DocumentMeta? result = await store.GetDocumentMetaAsync("doc-123");

        result.Should().NotBeNull();
        result!.DocumentId.Should().Be("doc-123");
        result.CreatedAt.Should().Be("2024-01-01T00:00:00Z");
        result.LastModifiedAt.Should().Be("2024-01-02T12:00:00Z");
        result.LastModifiedBy.Should().Be("user-1");
        result.Version.Should().Be(42);
    }

    [Fact]
    public async Task CreateSnapshot_ShouldCreateAndStoreSnapshot()
    {
        byte[] state = new byte[] { 10, 20, 30 };
        mockRedis.Setup(r => r.ListLengthAsync(It.IsAny<string>())).ReturnsAsync(1);

        DocumentSnapshot snapshot = await store.CreateSnapshotAsync("doc-123", state, "user-1", "Version 1");

        snapshot.DocumentId.Should().Be("doc-123");
        snapshot.CreatedBy.Should().Be("user-1");
        snapshot.Label.Should().Be("Version 1");
        snapshot.Id.Should().NotBeNullOrEmpty();
        snapshot.CreatedAt.Should().NotBeNullOrEmpty();
        snapshot.State.Should().Be(Convert.ToBase64String(state));
        mockRedis.Verify(r => r.ListPushAsync("doc:snapshots:doc-123", It.IsAny<string>()), Times.Once);
    }

    [Fact]
    public async Task CreateSnapshot_ShouldTrimWhenExceedingMax()
    {
        byte[] state = new byte[] { 1 };
        mockRedis.Setup(r => r.ListLengthAsync("doc:snapshots:doc-123")).ReturnsAsync(55);

        await store.CreateSnapshotAsync("doc-123", state, "user-1");

        mockRedis.Verify(r => r.ListTrimAsync("doc:snapshots:doc-123", 0, 49), Times.Once);
    }

    [Fact]
    public async Task CreateSnapshot_ShouldNotTrimWhenUnderMax()
    {
        byte[] state = new byte[] { 1 };
        mockRedis.Setup(r => r.ListLengthAsync(It.IsAny<string>())).ReturnsAsync(10);

        await store.CreateSnapshotAsync("doc-123", state, "user-1");

        mockRedis.Verify(r => r.ListTrimAsync(It.IsAny<string>(), It.IsAny<long>(), It.IsAny<long>()), Times.Never);
    }

    [Fact]
    public async Task GetSnapshots_ShouldReturnParsedSnapshots()
    {
        var snapshots = new[]
        {
            JsonSerializer.Serialize(new DocumentSnapshot
            {
                Id = "snap-1",
                DocumentId = "doc-123",
                State = Convert.ToBase64String(new byte[] { 1, 2 }),
                CreatedAt = "2024-01-01T00:00:00Z",
                CreatedBy = "user-1",
                Label = "First",
            }),
            JsonSerializer.Serialize(new DocumentSnapshot
            {
                Id = "snap-2",
                DocumentId = "doc-123",
                State = Convert.ToBase64String(new byte[] { 3, 4 }),
                CreatedAt = "2024-01-02T00:00:00Z",
                CreatedBy = "user-2",
            }),
        };
        mockRedis.Setup(r => r.ListRangeAsync("doc:snapshots:doc-123", 0, 9)).ReturnsAsync(snapshots);

        List<DocumentSnapshot> result = await store.GetSnapshotsAsync("doc-123", 10);

        result.Should().HaveCount(2);
        result[0].Id.Should().Be("snap-1");
        result[0].Label.Should().Be("First");
        result[1].Id.Should().Be("snap-2");
    }

    [Fact]
    public async Task GetSnapshots_ShouldReturnEmptyWhenNoSnapshots()
    {
        mockRedis.Setup(r => r.ListRangeAsync(It.IsAny<string>(), It.IsAny<long>(), It.IsAny<long>())).ReturnsAsync(Array.Empty<string>());

        List<DocumentSnapshot> result = await store.GetSnapshotsAsync("doc-none");

        result.Should().BeEmpty();
    }

    [Fact]
    public async Task GetSnapshotState_ShouldReturnStateForSpecificSnapshot()
    {
        byte[] stateBytes = new byte[] { 10, 20, 30 };
        var snapshot = new DocumentSnapshot
        {
            Id = "snap-target",
            DocumentId = "doc-123",
            State = Convert.ToBase64String(stateBytes),
            CreatedAt = "2024-01-01T00:00:00Z",
            CreatedBy = "user-1",
        };
        mockRedis.Setup(r => r.ListRangeAsync(It.IsAny<string>(), It.IsAny<long>(), It.IsAny<long>()))
            .ReturnsAsync(new[] { JsonSerializer.Serialize(snapshot) });

        byte[]? result = await store.GetSnapshotStateAsync("doc-123", "snap-target");

        result.Should().NotBeNull();
        result.Should().BeEquivalentTo(stateBytes);
    }

    [Fact]
    public async Task GetSnapshotState_ShouldReturnNullForNonExistentSnapshot()
    {
        mockRedis.Setup(r => r.ListRangeAsync(It.IsAny<string>(), It.IsAny<long>(), It.IsAny<long>())).ReturnsAsync(Array.Empty<string>());

        byte[]? result = await store.GetSnapshotStateAsync("doc-123", "snap-missing");

        result.Should().BeNull();
    }
}
