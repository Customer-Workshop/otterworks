using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Microsoft.Extensions.Options;
using OtterWorks.NotificationService.Config;
using OtterWorks.NotificationService.Models;

namespace OtterWorks.NotificationService.Services;

public class DynamoDbNotificationRepository : INotificationRepository
{
    private readonly IAmazonDynamoDB _dynamoDb;
    private readonly AwsSettings _settings;
    private readonly ILogger<DynamoDbNotificationRepository> _logger;

    public DynamoDbNotificationRepository(
        IAmazonDynamoDB dynamoDb,
        IOptions<AwsSettings> settings,
        ILogger<DynamoDbNotificationRepository> logger)
    {
        _dynamoDb = dynamoDb;
        _settings = settings.Value;
        _logger = logger;
    }

    public async Task SaveNotificationAsync(Notification notification)
    {
        var item = new Dictionary<string, AttributeValue>
        {
            ["id"] = new AttributeValue { S = notification.Id },
            ["userId"] = new AttributeValue { S = notification.UserId },
            ["type"] = new AttributeValue { S = notification.Type },
            ["title"] = new AttributeValue { S = notification.Title },
            ["message"] = new AttributeValue { S = notification.Message },
            ["resourceId"] = new AttributeValue { S = notification.ResourceId },
            ["resourceType"] = new AttributeValue { S = notification.ResourceType },
            ["actorId"] = new AttributeValue { S = notification.ActorId },
            ["read"] = new AttributeValue { BOOL = notification.Read },
            ["deliveredVia"] = new AttributeValue { L = notification.DeliveredVia.Select(v => new AttributeValue { S = v }).ToList() },
            ["createdAt"] = new AttributeValue { S = notification.CreatedAt },
        };

        var request = new PutItemRequest
        {
            TableName = _settings.DynamoDbTableNotifications,
            Item = item,
        };

        await _dynamoDb.PutItemAsync(request);
        _logger.LogDebug("Saved notification {Id} for user {UserId}", notification.Id, notification.UserId);
    }

    public async Task<Notification?> GetNotificationByIdAsync(string id)
    {
        var request = new GetItemRequest
        {
            TableName = _settings.DynamoDbTableNotifications,
            Key = new Dictionary<string, AttributeValue>
            {
                ["id"] = new AttributeValue { S = id },
            },
        };

        var response = await _dynamoDb.GetItemAsync(request);
        if (response.Item is null || response.Item.Count == 0)
        {
            return null;
        }

        return MapToNotification(response.Item);
    }

    public async Task<(List<Notification> Notifications, int Total)> GetNotificationsByUserIdAsync(
        string userId, int page = 1, int pageSize = 20)
    {
        var allItems = new List<Notification>();
        Dictionary<string, AttributeValue>? lastEvaluatedKey = null;

        do
        {
            var request = new QueryRequest
            {
                TableName = _settings.DynamoDbTableNotifications,
                IndexName = "userId-createdAt-index",
                KeyConditionExpression = "userId = :uid",
                ExpressionAttributeValues = new Dictionary<string, AttributeValue>
                {
                    [":uid"] = new AttributeValue { S = userId },
                },
                ScanIndexForward = false,
            };

            if (lastEvaluatedKey is not null)
            {
                request.ExclusiveStartKey = lastEvaluatedKey;
            }

            var response = await _dynamoDb.QueryAsync(request);
            foreach (var item in response.Items)
            {
                var notification = MapToNotification(item);
                if (notification is not null)
                {
                    allItems.Add(notification);
                }
            }

            lastEvaluatedKey = response.LastEvaluatedKey?.Count > 0 ? response.LastEvaluatedKey : null;
        }
        while (lastEvaluatedKey is not null);

        var total = allItems.Count;
        var startIndex = (page - 1) * pageSize;
        var paged = allItems.Skip(startIndex).Take(pageSize).ToList();

        return (paged, total);
    }

    public async Task<int> GetUnreadCountAsync(string userId)
    {
        var totalCount = 0;
        Dictionary<string, AttributeValue>? lastEvaluatedKey = null;

        do
        {
            var request = new QueryRequest
            {
                TableName = _settings.DynamoDbTableNotifications,
                IndexName = "userId-createdAt-index",
                KeyConditionExpression = "userId = :uid",
                FilterExpression = "#r = :readVal",
                ExpressionAttributeNames = new Dictionary<string, string>
                {
                    ["#r"] = "read",
                },
                ExpressionAttributeValues = new Dictionary<string, AttributeValue>
                {
                    [":uid"] = new AttributeValue { S = userId },
                    [":readVal"] = new AttributeValue { BOOL = false },
                },
            };

            if (lastEvaluatedKey is not null)
            {
                request.ExclusiveStartKey = lastEvaluatedKey;
            }

            var response = await _dynamoDb.QueryAsync(request);
            totalCount += response.Count;
            lastEvaluatedKey = response.LastEvaluatedKey?.Count > 0 ? response.LastEvaluatedKey : null;
        }
        while (lastEvaluatedKey is not null);

        return totalCount;
    }

    public async Task<bool> MarkAsReadAsync(string id)
    {
        var request = new UpdateItemRequest
        {
            TableName = _settings.DynamoDbTableNotifications,
            Key = new Dictionary<string, AttributeValue>
            {
                ["id"] = new AttributeValue { S = id },
            },
            UpdateExpression = "SET #r = :readVal",
            ExpressionAttributeNames = new Dictionary<string, string>
            {
                ["#r"] = "read",
            },
            ExpressionAttributeValues = new Dictionary<string, AttributeValue>
            {
                [":readVal"] = new AttributeValue { BOOL = true },
            },
            ConditionExpression = "attribute_exists(id)",
        };

        try
        {
            await _dynamoDb.UpdateItemAsync(request);
            _logger.LogDebug("Marked notification {Id} as read", id);
            return true;
        }
        catch (ConditionalCheckFailedException)
        {
            _logger.LogWarning("Failed to mark notification {Id} as read: not found", id);
            return false;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to mark notification {Id} as read", id);
            return false;
        }
    }

    public async Task<int> MarkAllAsReadAsync(string userId)
    {
        var (notifications, _) = await GetNotificationsByUserIdAsync(userId, page: 1, pageSize: int.MaxValue);
        var unreadNotifications = notifications.Where(n => !n.Read).ToList();

        foreach (var notification in unreadNotifications)
        {
            await MarkAsReadAsync(notification.Id);
        }

        _logger.LogInformation("Marked {Count} notifications as read for user {UserId}", unreadNotifications.Count, userId);
        return unreadNotifications.Count;
    }

    public async Task<bool> DeleteNotificationAsync(string id)
    {
        var request = new DeleteItemRequest
        {
            TableName = _settings.DynamoDbTableNotifications,
            Key = new Dictionary<string, AttributeValue>
            {
                ["id"] = new AttributeValue { S = id },
            },
        };

        try
        {
            await _dynamoDb.DeleteItemAsync(request);
            _logger.LogDebug("Deleted notification {Id}", id);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to delete notification {Id}", id);
            return false;
        }
    }

    public async Task<NotificationPreference> GetPreferencesAsync(string userId)
    {
        var request = new GetItemRequest
        {
            TableName = _settings.DynamoDbTablePreferences,
            Key = new Dictionary<string, AttributeValue>
            {
                ["userId"] = new AttributeValue { S = userId },
            },
        };

        var response = await _dynamoDb.GetItemAsync(request);
        if (response.Item is null || response.Item.Count == 0)
        {
            return new NotificationPreference { UserId = userId };
        }

        return MapToPreference(response.Item) ?? new NotificationPreference { UserId = userId };
    }

    public async Task SavePreferencesAsync(NotificationPreference preference)
    {
        var channelsMap = preference.Channels.ToDictionary(
            kvp => kvp.Key,
            kvp => new AttributeValue
            {
                L = kvp.Value.Select(c => new AttributeValue { S = c.ToString() }).ToList(),
            });

        var item = new Dictionary<string, AttributeValue>
        {
            ["userId"] = new AttributeValue { S = preference.UserId },
            ["channels"] = new AttributeValue { M = channelsMap },
        };

        var request = new PutItemRequest
        {
            TableName = _settings.DynamoDbTablePreferences,
            Item = item,
        };

        await _dynamoDb.PutItemAsync(request);
        _logger.LogDebug("Saved preferences for user {UserId}", preference.UserId);
    }

    private static Notification? MapToNotification(Dictionary<string, AttributeValue> item)
    {
        try
        {
            if (!item.TryGetValue("id", out var idAttr) || idAttr.S is null)
            {
                return null;
            }

            if (!item.TryGetValue("userId", out var userIdAttr) || userIdAttr.S is null)
            {
                return null;
            }

            return new Notification
            {
                Id = idAttr.S,
                UserId = userIdAttr.S,
                Type = item.TryGetValue("type", out var typeAttr) ? typeAttr.S ?? string.Empty : string.Empty,
                Title = item.TryGetValue("title", out var titleAttr) ? titleAttr.S ?? string.Empty : string.Empty,
                Message = item.TryGetValue("message", out var msgAttr) ? msgAttr.S ?? string.Empty : string.Empty,
                ResourceId = item.TryGetValue("resourceId", out var resIdAttr) ? resIdAttr.S ?? string.Empty : string.Empty,
                ResourceType = item.TryGetValue("resourceType", out var resTypeAttr) ? resTypeAttr.S ?? string.Empty : string.Empty,
                ActorId = item.TryGetValue("actorId", out var actorAttr) ? actorAttr.S ?? string.Empty : string.Empty,
                Read = item.TryGetValue("read", out var readAttr) && readAttr.BOOL,
                DeliveredVia = item.TryGetValue("deliveredVia", out var dvAttr) && dvAttr.L is not null
                    ? dvAttr.L.Where(v => v.S is not null).Select(v => v.S).ToList()
                    : new List<string>(),
                CreatedAt = item.TryGetValue("createdAt", out var caAttr) ? caAttr.S ?? string.Empty : string.Empty,
            };
        }
        catch
        {
            return null;
        }
    }

    private static NotificationPreference? MapToPreference(Dictionary<string, AttributeValue> item)
    {
        try
        {
            if (!item.TryGetValue("userId", out var userIdAttr) || userIdAttr.S is null)
            {
                return null;
            }

            var channels = new Dictionary<string, List<DeliveryChannel>>();

            if (item.TryGetValue("channels", out var channelsAttr) && channelsAttr.M is not null)
            {
                foreach (var kvp in channelsAttr.M)
                {
                    if (kvp.Value.L is not null)
                    {
                        var channelList = new List<DeliveryChannel>();
                        foreach (var attr in kvp.Value.L)
                        {
                            if (attr.S is not null && Enum.TryParse<DeliveryChannel>(attr.S, out var channel))
                            {
                                channelList.Add(channel);
                            }
                        }

                        channels[kvp.Key] = channelList;
                    }
                }
            }

            return new NotificationPreference
            {
                UserId = userIdAttr.S,
                Channels = channels,
            };
        }
        catch
        {
            return null;
        }
    }
}
