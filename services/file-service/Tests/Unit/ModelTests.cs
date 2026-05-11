using System.Text.Json;
using OtterWorks.FileService.Models;

namespace FileService.Tests.Unit;

public class ModelTests
{
    [Fact]
    public void FileMetadata_SerializesWithSnakeCaseProperties()
    {
        var meta = new FileMetadata
        {
            Id = Guid.NewGuid(),
            Name = "doc.pdf",
            MimeType = "application/pdf",
            SizeBytes = 5000,
            S3Key = "files/test",
            OwnerId = Guid.NewGuid(),
            Version = 1,
            IsTrashed = false,
            CreatedAt = DateTime.UtcNow,
            UpdatedAt = DateTime.UtcNow,
        };

        var json = JsonSerializer.Serialize(meta);
        Assert.Contains("\"mime_type\"", json);
        Assert.Contains("\"size_bytes\"", json);
        Assert.Contains("\"s3_key\"", json);
        Assert.Contains("\"owner_id\"", json);
        Assert.Contains("\"is_trashed\"", json);
        Assert.Contains("\"created_at\"", json);
        Assert.Contains("\"updated_at\"", json);
    }

    [Fact]
    public void FileShare_SerializesPermissionAsString()
    {
        var share = new FileShare
        {
            Id = Guid.NewGuid(),
            FileId = Guid.NewGuid(),
            SharedWith = Guid.NewGuid(),
            Permission = SharePermission.Viewer,
            SharedBy = Guid.NewGuid(),
            CreatedAt = DateTime.UtcNow,
        };

        var json = JsonSerializer.Serialize(share);
        Assert.Contains("\"viewer\"", json);
    }

    [Fact]
    public void UploadResponse_ContainsFileProperty()
    {
        var resp = new UploadResponse
        {
            File = new FileMetadata { Name = "test.txt" },
        };

        var json = JsonSerializer.Serialize(resp);
        Assert.Contains("\"file\"", json);
        Assert.Contains("test.txt", json);
    }

    [Fact]
    public void DownloadResponse_ContainsUrlAndExpiry()
    {
        var resp = new DownloadResponse
        {
            Url = "https://example.com/file",
            ExpiresInSecs = 3600,
        };

        var json = JsonSerializer.Serialize(resp);
        Assert.Contains("\"url\"", json);
        Assert.Contains("\"expires_in_secs\"", json);
    }

    [Fact]
    public void ErrorResponse_SerializesCorrectly()
    {
        var err = new ErrorResponse
        {
            Error = "not_found",
            Message = "File not found",
        };

        var json = JsonSerializer.Serialize(err);
        Assert.Contains("\"error\"", json);
        Assert.Contains("\"message\"", json);
    }

    [Fact]
    public void ActivityItem_SerializesTypeField()
    {
        var item = new ActivityItem
        {
            Id = "upload-1",
            Type = "upload",
            Description = "Uploaded file",
            ActorName = "You",
            ResourceName = "test.txt",
            ResourceType = "file",
            ResourceId = "abc",
            CreatedAt = DateTime.UtcNow.ToString("o"),
        };

        var json = JsonSerializer.Serialize(item);
        Assert.Contains("\"type\"", json);
        Assert.Contains("\"actor_name\"", json);
        Assert.Contains("\"resource_name\"", json);
    }

    [Fact]
    public void ListFilesResponse_SerializesCorrectly()
    {
        var resp = new ListFilesResponse
        {
            Files = new List<FileMetadata> { new() { Name = "a.txt" } },
            Total = 1,
            Page = 1,
            PageSize = 50,
        };

        var json = JsonSerializer.Serialize(resp);
        Assert.Contains("\"page_size\"", json);
        Assert.Contains("\"total\"", json);
    }

    [Fact]
    public void FileDetailResponse_InheritsFileMetadata()
    {
        var resp = new FileDetailResponse
        {
            Id = Guid.NewGuid(),
            Name = "shared-doc.pdf",
            SharedWith = new List<FileShare>(),
        };

        var json = JsonSerializer.Serialize(resp);
        Assert.Contains("\"shared_with\"", json);
        Assert.Contains("shared-doc.pdf", json);
    }
}
