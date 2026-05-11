using System.Globalization;
using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Microsoft.Extensions.Options;
using OtterWorks.FileService.Config;
using OtterWorks.FileService.Models;

namespace OtterWorks.FileService.Services;

public class DynamoDbMetadataService : IMetadataService
{
    private readonly IAmazonDynamoDB _dynamoDb;
    private readonly string _filesTable;
    private readonly string _foldersTable;
    private readonly string _versionsTable;
    private readonly string _sharesTable;
    private readonly ILogger<DynamoDbMetadataService> _logger;

    public DynamoDbMetadataService(IAmazonDynamoDB dynamoDb, IOptions<AwsSettings> settings, ILogger<DynamoDbMetadataService> logger)
    {
        _dynamoDb = dynamoDb;
        _filesTable = settings.Value.DynamoDbTable;
        _foldersTable = settings.Value.DynamoDbFoldersTable;
        _versionsTable = settings.Value.DynamoDbVersionsTable;
        _sharesTable = settings.Value.DynamoDbSharesTable;
        _logger = logger;
    }

    // -- File Metadata --

    public async Task PutFileAsync(FileMetadata file)
    {
        var item = new Dictionary<string, AttributeValue>
        {
            ["id"] = new(file.Id.ToString()),
            ["name"] = new(file.Name),
            ["mime_type"] = new(file.MimeType),
            ["size_bytes"] = new() { N = file.SizeBytes.ToString() },
            ["s3_key"] = new(file.S3Key),
            ["owner_id"] = new(file.OwnerId.ToString()),
            ["version"] = new() { N = file.Version.ToString() },
            ["is_trashed"] = new() { BOOL = file.IsTrashed },
            ["created_at"] = new(file.CreatedAt.ToString("o")),
            ["updated_at"] = new(file.UpdatedAt.ToString("o")),
        };

        if (file.FolderId.HasValue)
        {
            item["folder_id"] = new AttributeValue(file.FolderId.Value.ToString());
        }

        await _dynamoDb.PutItemAsync(new PutItemRequest
        {
            TableName = _filesTable,
            Item = item,
        });
    }

    public async Task<FileMetadata?> GetFileAsync(Guid fileId)
    {
        var response = await _dynamoDb.GetItemAsync(new GetItemRequest
        {
            TableName = _filesTable,
            Key = new Dictionary<string, AttributeValue>
            {
                ["id"] = new(fileId.ToString()),
            },
        });

        if (response.Item == null || response.Item.Count == 0)
        {
            return null;
        }

        return ParseFileMetadata(response.Item);
    }

    public async Task DeleteFileAsync(Guid fileId)
    {
        await _dynamoDb.DeleteItemAsync(new DeleteItemRequest
        {
            TableName = _filesTable,
            Key = new Dictionary<string, AttributeValue>
            {
                ["id"] = new(fileId.ToString()),
            },
        });
    }

    public async Task<FileMetadata?> TrashFileAsync(Guid fileId)
    {
        var now = DateTime.UtcNow;
        try
        {
            await _dynamoDb.UpdateItemAsync(new UpdateItemRequest
            {
                TableName = _filesTable,
                Key = new Dictionary<string, AttributeValue>
                {
                    ["id"] = new(fileId.ToString()),
                },
                UpdateExpression = "SET is_trashed = :t, updated_at = :u",
                ConditionExpression = "attribute_exists(id)",
                ExpressionAttributeValues = new Dictionary<string, AttributeValue>
                {
                    [":t"] = new() { BOOL = true },
                    [":u"] = new(now.ToString("o")),
                },
            });
        }
        catch (ConditionalCheckFailedException)
        {
            return null;
        }

        return await GetFileAsync(fileId);
    }

    public async Task<FileMetadata?> RestoreFileAsync(Guid fileId)
    {
        var now = DateTime.UtcNow;
        try
        {
            await _dynamoDb.UpdateItemAsync(new UpdateItemRequest
            {
                TableName = _filesTable,
                Key = new Dictionary<string, AttributeValue>
                {
                    ["id"] = new(fileId.ToString()),
                },
                UpdateExpression = "SET is_trashed = :t, updated_at = :u",
                ConditionExpression = "attribute_exists(id)",
                ExpressionAttributeValues = new Dictionary<string, AttributeValue>
                {
                    [":t"] = new() { BOOL = false },
                    [":u"] = new(now.ToString("o")),
                },
            });
        }
        catch (ConditionalCheckFailedException)
        {
            return null;
        }

        return await GetFileAsync(fileId);
    }

    public async Task<FileMetadata?> RenameFileAsync(Guid fileId, string name)
    {
        var now = DateTime.UtcNow;
        try
        {
            await _dynamoDb.UpdateItemAsync(new UpdateItemRequest
            {
                TableName = _filesTable,
                Key = new Dictionary<string, AttributeValue>
                {
                    ["id"] = new(fileId.ToString()),
                },
                UpdateExpression = "SET #n = :n, updated_at = :u",
                ConditionExpression = "attribute_exists(id)",
                ExpressionAttributeNames = new Dictionary<string, string>
                {
                    ["#n"] = "name",
                },
                ExpressionAttributeValues = new Dictionary<string, AttributeValue>
                {
                    [":n"] = new(name),
                    [":u"] = new(now.ToString("o")),
                },
            });
        }
        catch (ConditionalCheckFailedException)
        {
            return null;
        }

        return await GetFileAsync(fileId);
    }

    public async Task<FileMetadata?> MoveFileAsync(Guid fileId, Guid? folderId)
    {
        var now = DateTime.UtcNow;
        var request = new UpdateItemRequest
        {
            TableName = _filesTable,
            Key = new Dictionary<string, AttributeValue>
            {
                ["id"] = new(fileId.ToString()),
            },
            ConditionExpression = "attribute_exists(id)",
            ExpressionAttributeValues = new Dictionary<string, AttributeValue>
            {
                [":u"] = new(now.ToString("o")),
            },
        };

        if (folderId.HasValue)
        {
            request.UpdateExpression = "SET folder_id = :f, updated_at = :u";
            request.ExpressionAttributeValues[":f"] = new AttributeValue(folderId.Value.ToString());
        }
        else
        {
            request.UpdateExpression = "SET updated_at = :u REMOVE folder_id";
        }

        try
        {
            await _dynamoDb.UpdateItemAsync(request);
        }
        catch (ConditionalCheckFailedException)
        {
            return null;
        }

        return await GetFileAsync(fileId);
    }

    public async Task<List<FileMetadata>> ListFilesAsync(Guid? folderId, Guid? ownerId, bool includeTrashed)
    {
        var filterParts = new List<string>();
        var expressionValues = new Dictionary<string, AttributeValue>();

        if (folderId.HasValue)
        {
            filterParts.Add("folder_id = :folder_id");
            expressionValues[":folder_id"] = new AttributeValue(folderId.Value.ToString());
        }

        if (ownerId.HasValue)
        {
            filterParts.Add("owner_id = :owner_id");
            expressionValues[":owner_id"] = new AttributeValue(ownerId.Value.ToString());
        }

        if (!includeTrashed)
        {
            filterParts.Add("is_trashed = :trashed");
            expressionValues[":trashed"] = new AttributeValue { BOOL = false };
        }

        var request = new ScanRequest
        {
            TableName = _filesTable,
        };

        if (filterParts.Count > 0)
        {
            request.FilterExpression = string.Join(" AND ", filterParts);
            request.ExpressionAttributeValues = expressionValues;
        }

        var files = new List<FileMetadata>();
        ScanResponse response;
        do
        {
            response = await _dynamoDb.ScanAsync(request);
            foreach (var item in response.Items)
            {
                files.Add(ParseFileMetadata(item));
            }

            request.ExclusiveStartKey = response.LastEvaluatedKey;
        }
        while (response.LastEvaluatedKey != null && response.LastEvaluatedKey.Count > 0);

        return files;
    }

    public async Task<List<FileMetadata>> ListTrashedAsync(Guid? ownerId)
    {
        var filterParts = new List<string> { "is_trashed = :trashed" };
        var expressionValues = new Dictionary<string, AttributeValue>
        {
            [":trashed"] = new() { BOOL = true },
        };

        if (ownerId.HasValue)
        {
            filterParts.Add("owner_id = :owner_id");
            expressionValues[":owner_id"] = new AttributeValue(ownerId.Value.ToString());
        }

        var request = new ScanRequest
        {
            TableName = _filesTable,
            FilterExpression = string.Join(" AND ", filterParts),
            ExpressionAttributeValues = expressionValues,
        };

        var files = new List<FileMetadata>();
        ScanResponse response;
        do
        {
            response = await _dynamoDb.ScanAsync(request);
            foreach (var item in response.Items)
            {
                files.Add(ParseFileMetadata(item));
            }

            request.ExclusiveStartKey = response.LastEvaluatedKey;
        }
        while (response.LastEvaluatedKey != null && response.LastEvaluatedKey.Count > 0);

        files.Sort((a, b) => b.UpdatedAt.CompareTo(a.UpdatedAt));
        return files;
    }

    // -- Folders --

    public async Task PutFolderAsync(Folder folder)
    {
        var item = new Dictionary<string, AttributeValue>
        {
            ["id"] = new(folder.Id.ToString()),
            ["name"] = new(folder.Name),
            ["owner_id"] = new(folder.OwnerId.ToString()),
            ["created_at"] = new(folder.CreatedAt.ToString("o")),
            ["updated_at"] = new(folder.UpdatedAt.ToString("o")),
        };

        if (folder.ParentId.HasValue)
        {
            item["parent_id"] = new AttributeValue(folder.ParentId.Value.ToString());
        }

        await _dynamoDb.PutItemAsync(new PutItemRequest
        {
            TableName = _foldersTable,
            Item = item,
        });
    }

    public async Task<Folder?> GetFolderAsync(Guid folderId)
    {
        var response = await _dynamoDb.GetItemAsync(new GetItemRequest
        {
            TableName = _foldersTable,
            Key = new Dictionary<string, AttributeValue>
            {
                ["id"] = new(folderId.ToString()),
            },
        });

        if (response.Item == null || response.Item.Count == 0)
        {
            return null;
        }

        return ParseFolder(response.Item);
    }

    public async Task<Folder?> UpdateFolderAsync(Guid folderId, string? name, Guid? parentId)
    {
        var now = DateTime.UtcNow;
        var updateParts = new List<string> { "updated_at = :u" };
        var expressionValues = new Dictionary<string, AttributeValue>
        {
            [":u"] = new(now.ToString("o")),
        };
        var expressionNames = new Dictionary<string, string>();

        if (name != null)
        {
            updateParts.Add("#n = :n");
            expressionNames["#n"] = "name";
            expressionValues[":n"] = new AttributeValue(name);
        }

        if (parentId.HasValue)
        {
            updateParts.Add("parent_id = :p");
            expressionValues[":p"] = new AttributeValue(parentId.Value.ToString());
        }

        var request = new UpdateItemRequest
        {
            TableName = _foldersTable,
            Key = new Dictionary<string, AttributeValue>
            {
                ["id"] = new(folderId.ToString()),
            },
            UpdateExpression = "SET " + string.Join(", ", updateParts),
            ConditionExpression = "attribute_exists(id)",
            ExpressionAttributeValues = expressionValues,
        };

        if (expressionNames.Count > 0)
        {
            request.ExpressionAttributeNames = expressionNames;
        }

        try
        {
            await _dynamoDb.UpdateItemAsync(request);
        }
        catch (ConditionalCheckFailedException)
        {
            return null;
        }

        return await GetFolderAsync(folderId);
    }

    public async Task DeleteFolderAsync(Guid folderId)
    {
        await _dynamoDb.DeleteItemAsync(new DeleteItemRequest
        {
            TableName = _foldersTable,
            Key = new Dictionary<string, AttributeValue>
            {
                ["id"] = new(folderId.ToString()),
            },
        });
    }

    public async Task<List<Folder>> ListFoldersAsync(Guid? parentId, Guid? ownerId)
    {
        var filterParts = new List<string>();
        var expressionValues = new Dictionary<string, AttributeValue>();

        if (parentId.HasValue)
        {
            filterParts.Add("parent_id = :parent_id");
            expressionValues[":parent_id"] = new AttributeValue(parentId.Value.ToString());
        }
        else
        {
            filterParts.Add("attribute_not_exists(parent_id)");
        }

        if (ownerId.HasValue)
        {
            filterParts.Add("owner_id = :owner_id");
            expressionValues[":owner_id"] = new AttributeValue(ownerId.Value.ToString());
        }

        var request = new ScanRequest
        {
            TableName = _foldersTable,
        };

        if (filterParts.Count > 0)
        {
            request.FilterExpression = string.Join(" AND ", filterParts);
        }

        if (expressionValues.Count > 0)
        {
            request.ExpressionAttributeValues = expressionValues;
        }

        var folders = new List<Folder>();
        ScanResponse response;
        do
        {
            response = await _dynamoDb.ScanAsync(request);
            foreach (var item in response.Items)
            {
                folders.Add(ParseFolder(item));
            }

            request.ExclusiveStartKey = response.LastEvaluatedKey;
        }
        while (response.LastEvaluatedKey != null && response.LastEvaluatedKey.Count > 0);

        return folders;
    }

    // -- File Versions --

    public async Task PutVersionAsync(FileVersion version)
    {
        var item = new Dictionary<string, AttributeValue>
        {
            ["file_id"] = new(version.FileId.ToString()),
            ["version"] = new() { N = version.Version.ToString() },
            ["s3_key"] = new(version.S3Key),
            ["size_bytes"] = new() { N = version.SizeBytes.ToString() },
            ["created_by"] = new(version.CreatedBy.ToString()),
            ["created_at"] = new(version.CreatedAt.ToString("o")),
        };

        await _dynamoDb.PutItemAsync(new PutItemRequest
        {
            TableName = _versionsTable,
            Item = item,
        });
    }

    public async Task<List<FileVersion>> ListVersionsAsync(Guid fileId)
    {
        var response = await _dynamoDb.QueryAsync(new QueryRequest
        {
            TableName = _versionsTable,
            KeyConditionExpression = "file_id = :fid",
            ExpressionAttributeValues = new Dictionary<string, AttributeValue>
            {
                [":fid"] = new(fileId.ToString()),
            },
            ScanIndexForward = false,
        });

        return response.Items.Select(ParseFileVersion).ToList();
    }

    // -- File Shares --

    public async Task PutShareAsync(FileShare share)
    {
        var item = new Dictionary<string, AttributeValue>
        {
            ["id"] = new(share.Id.ToString()),
            ["file_id"] = new(share.FileId.ToString()),
            ["shared_with"] = new(share.SharedWith.ToString()),
            ["permission"] = new(share.Permission.ToString().ToLowerInvariant()),
            ["shared_by"] = new(share.SharedBy.ToString()),
            ["created_at"] = new(share.CreatedAt.ToString("o")),
        };

        await _dynamoDb.PutItemAsync(new PutItemRequest
        {
            TableName = _sharesTable,
            Item = item,
        });
    }

    public async Task<FileShare?> FindExistingShareAsync(Guid fileId, Guid sharedWith)
    {
        var request = new ScanRequest
        {
            TableName = _sharesTable,
            FilterExpression = "file_id = :fid AND shared_with = :uid",
            ExpressionAttributeValues = new Dictionary<string, AttributeValue>
            {
                [":fid"] = new(fileId.ToString()),
                [":uid"] = new(sharedWith.ToString()),
            },
        };

        var response = await _dynamoDb.ScanAsync(request);
        if (response.Items.Count > 0)
        {
            return ParseFileShare(response.Items[0]);
        }

        return null;
    }

    public async Task<List<FileShare>> ListSharesForUserAsync(Guid userId)
    {
        var request = new ScanRequest
        {
            TableName = _sharesTable,
            FilterExpression = "shared_with = :uid",
            ExpressionAttributeValues = new Dictionary<string, AttributeValue>
            {
                [":uid"] = new(userId.ToString()),
            },
        };

        var shares = new List<FileShare>();
        ScanResponse response;
        do
        {
            response = await _dynamoDb.ScanAsync(request);
            foreach (var item in response.Items)
            {
                shares.Add(ParseFileShare(item));
            }

            request.ExclusiveStartKey = response.LastEvaluatedKey;
        }
        while (response.LastEvaluatedKey != null && response.LastEvaluatedKey.Count > 0);

        return shares;
    }

    public async Task<List<FileShare>> ListSharesByOwnerAsync(Guid ownerId)
    {
        var request = new ScanRequest
        {
            TableName = _sharesTable,
            FilterExpression = "shared_by = :uid",
            ExpressionAttributeValues = new Dictionary<string, AttributeValue>
            {
                [":uid"] = new(ownerId.ToString()),
            },
        };

        var shares = new List<FileShare>();
        ScanResponse response;
        do
        {
            response = await _dynamoDb.ScanAsync(request);
            foreach (var item in response.Items)
            {
                shares.Add(ParseFileShare(item));
            }

            request.ExclusiveStartKey = response.LastEvaluatedKey;
        }
        while (response.LastEvaluatedKey != null && response.LastEvaluatedKey.Count > 0);

        return shares;
    }

    public async Task DeleteShareAsync(Guid shareId)
    {
        await _dynamoDb.DeleteItemAsync(new DeleteItemRequest
        {
            TableName = _sharesTable,
            Key = new Dictionary<string, AttributeValue>
            {
                ["id"] = new(shareId.ToString()),
            },
        });
    }

    public async Task<List<FileShare>> ListSharesAsync(Guid fileId)
    {
        var request = new ScanRequest
        {
            TableName = _sharesTable,
            FilterExpression = "file_id = :fid",
            ExpressionAttributeValues = new Dictionary<string, AttributeValue>
            {
                [":fid"] = new(fileId.ToString()),
            },
        };

        var shares = new List<FileShare>();
        ScanResponse response;
        do
        {
            response = await _dynamoDb.ScanAsync(request);
            foreach (var item in response.Items)
            {
                shares.Add(ParseFileShare(item));
            }

            request.ExclusiveStartKey = response.LastEvaluatedKey;
        }
        while (response.LastEvaluatedKey != null && response.LastEvaluatedKey.Count > 0);

        return shares;
    }

    // -- Parsing Helpers --

    internal static FileMetadata ParseFileMetadata(Dictionary<string, AttributeValue> item)
    {
        return new FileMetadata
        {
            Id = Guid.Parse(item["id"].S),
            Name = item["name"].S,
            MimeType = item["mime_type"].S,
            SizeBytes = long.Parse(item["size_bytes"].N, CultureInfo.InvariantCulture),
            S3Key = item["s3_key"].S,
            FolderId = item.TryGetValue("folder_id", out var fid) && fid.S != null ? Guid.Parse(fid.S) : null,
            OwnerId = Guid.Parse(item["owner_id"].S),
            Version = int.Parse(item["version"].N, CultureInfo.InvariantCulture),
            IsTrashed = item["is_trashed"].BOOL,
            CreatedAt = DateTime.Parse(item["created_at"].S, CultureInfo.InvariantCulture).ToUniversalTime(),
            UpdatedAt = DateTime.Parse(item["updated_at"].S, CultureInfo.InvariantCulture).ToUniversalTime(),
        };
    }

    internal static Folder ParseFolder(Dictionary<string, AttributeValue> item)
    {
        return new Folder
        {
            Id = Guid.Parse(item["id"].S),
            Name = item["name"].S,
            ParentId = item.TryGetValue("parent_id", out var pid) && pid.S != null ? Guid.Parse(pid.S) : null,
            OwnerId = Guid.Parse(item["owner_id"].S),
            CreatedAt = DateTime.Parse(item["created_at"].S, CultureInfo.InvariantCulture).ToUniversalTime(),
            UpdatedAt = DateTime.Parse(item["updated_at"].S, CultureInfo.InvariantCulture).ToUniversalTime(),
        };
    }

    internal static FileVersion ParseFileVersion(Dictionary<string, AttributeValue> item)
    {
        return new FileVersion
        {
            FileId = Guid.Parse(item["file_id"].S),
            Version = int.Parse(item["version"].N, CultureInfo.InvariantCulture),
            S3Key = item["s3_key"].S,
            SizeBytes = long.Parse(item["size_bytes"].N, CultureInfo.InvariantCulture),
            CreatedBy = Guid.Parse(item["created_by"].S),
            CreatedAt = DateTime.Parse(item["created_at"].S, CultureInfo.InvariantCulture).ToUniversalTime(),
        };
    }

    internal static FileShare ParseFileShare(Dictionary<string, AttributeValue> item)
    {
        return new FileShare
        {
            Id = Guid.Parse(item["id"].S),
            FileId = Guid.Parse(item["file_id"].S),
            SharedWith = Guid.Parse(item["shared_with"].S),
            Permission = Enum.Parse<SharePermission>(item["permission"].S, ignoreCase: true),
            SharedBy = Guid.Parse(item["shared_by"].S),
            CreatedAt = DateTime.Parse(item["created_at"].S, CultureInfo.InvariantCulture).ToUniversalTime(),
        };
    }
}
