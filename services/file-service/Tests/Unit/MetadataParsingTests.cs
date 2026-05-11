using Amazon.DynamoDBv2.Model;
using OtterWorks.FileService.Models;
using OtterWorks.FileService.Services;

namespace FileService.Tests.Unit;

public class MetadataParsingTests
{
    private static Dictionary<string, AttributeValue> MakeFileItem()
    {
        var now = DateTime.UtcNow;
        var id = Guid.NewGuid();
        var owner = Guid.NewGuid();
        return new Dictionary<string, AttributeValue>
        {
            ["id"] = new(id.ToString()),
            ["name"] = new("test.txt"),
            ["mime_type"] = new("text/plain"),
            ["size_bytes"] = new() { N = "1024" },
            ["s3_key"] = new($"files/{id}"),
            ["owner_id"] = new(owner.ToString()),
            ["version"] = new() { N = "1" },
            ["is_trashed"] = new() { BOOL = false },
            ["created_at"] = new(now.ToString("o")),
            ["updated_at"] = new(now.ToString("o")),
        };
    }

    [Fact]
    public void ParseFileMetadata_Success()
    {
        var item = MakeFileItem();
        var file = DynamoDbMetadataService.ParseFileMetadata(item);

        Assert.Equal("test.txt", file.Name);
        Assert.Equal("text/plain", file.MimeType);
        Assert.Equal(1024, file.SizeBytes);
        Assert.Equal(1, file.Version);
        Assert.False(file.IsTrashed);
        Assert.Null(file.FolderId);
    }

    [Fact]
    public void ParseFileMetadata_WithFolder()
    {
        var item = MakeFileItem();
        var folderId = Guid.NewGuid();
        item["folder_id"] = new AttributeValue(folderId.ToString());

        var file = DynamoDbMetadataService.ParseFileMetadata(item);
        Assert.Equal(folderId, file.FolderId);
    }

    [Fact]
    public void ParseFileMetadata_MissingField_Throws()
    {
        var item = MakeFileItem();
        item.Remove("name");

        Assert.ThrowsAny<Exception>(() => DynamoDbMetadataService.ParseFileMetadata(item));
    }

    [Fact]
    public void ParseFolder_Success()
    {
        var now = DateTime.UtcNow;
        var id = Guid.NewGuid();
        var owner = Guid.NewGuid();
        var item = new Dictionary<string, AttributeValue>
        {
            ["id"] = new(id.ToString()),
            ["name"] = new("Documents"),
            ["owner_id"] = new(owner.ToString()),
            ["created_at"] = new(now.ToString("o")),
            ["updated_at"] = new(now.ToString("o")),
        };

        var folder = DynamoDbMetadataService.ParseFolder(item);
        Assert.Equal("Documents", folder.Name);
        Assert.Equal(id, folder.Id);
        Assert.Null(folder.ParentId);
    }

    [Fact]
    public void ParseFileVersion_Success()
    {
        var now = DateTime.UtcNow;
        var fileId = Guid.NewGuid();
        var userId = Guid.NewGuid();
        var item = new Dictionary<string, AttributeValue>
        {
            ["file_id"] = new(fileId.ToString()),
            ["version"] = new() { N = "3" },
            ["s3_key"] = new("files/v3/key"),
            ["size_bytes"] = new() { N = "2048" },
            ["created_by"] = new(userId.ToString()),
            ["created_at"] = new(now.ToString("o")),
        };

        var ver = DynamoDbMetadataService.ParseFileVersion(item);
        Assert.Equal(fileId, ver.FileId);
        Assert.Equal(3, ver.Version);
        Assert.Equal(2048, ver.SizeBytes);
    }

    [Fact]
    public void ParseFileShare_Success()
    {
        var now = DateTime.UtcNow;
        var shareId = Guid.NewGuid();
        var fileId = Guid.NewGuid();
        var userA = Guid.NewGuid();
        var userB = Guid.NewGuid();
        var item = new Dictionary<string, AttributeValue>
        {
            ["id"] = new(shareId.ToString()),
            ["file_id"] = new(fileId.ToString()),
            ["shared_with"] = new(userA.ToString()),
            ["permission"] = new("editor"),
            ["shared_by"] = new(userB.ToString()),
            ["created_at"] = new(now.ToString("o")),
        };

        var share = DynamoDbMetadataService.ParseFileShare(item);
        Assert.Equal(SharePermission.Editor, share.Permission);
        Assert.Equal(fileId, share.FileId);
    }

    [Fact]
    public void SharePermission_CaseInsensitiveParsing()
    {
        Assert.Equal(SharePermission.Viewer, Enum.Parse<SharePermission>("viewer", ignoreCase: true));
        Assert.Equal(SharePermission.Editor, Enum.Parse<SharePermission>("Editor", ignoreCase: true));
        Assert.False(Enum.TryParse<SharePermission>("invalid", ignoreCase: true, out _));
    }
}
