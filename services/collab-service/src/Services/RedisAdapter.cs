using OtterWorks.CollabService.Config;
using StackExchange.Redis;

namespace OtterWorks.CollabService.Services;

public class RedisAdapter : IRedisAdapter, IDisposable
{
    private readonly string keyPrefix;
    private readonly ILogger<RedisAdapter> logger;
    private readonly string connectionString;
    private ConnectionMultiplexer? connection;
    private IDatabase? db;
    private ISubscriber? subscriber;
    private bool disposed;

    public RedisAdapter(RedisSettings settings, ILogger<RedisAdapter> logger)
    {
        keyPrefix = settings.KeyPrefix;
        this.logger = logger;
        connectionString = settings.ConnectionString;
    }

    public async Task ConnectAsync()
    {
        connection = await ConnectionMultiplexer.ConnectAsync(connectionString);
        db = connection.GetDatabase();
        subscriber = connection.GetSubscriber();
        logger.LogInformation("Redis connected");
    }

    public async Task<byte[]?> GetAsync(string key)
    {
        if (db is null)
        {
            return null;
        }

        RedisValue value = await db.StringGetAsync(PrefixKey(key));
        return value.IsNullOrEmpty ? null : (byte[])value!;
    }

    public async Task SetAsync(string key, byte[] value, int? ttlSeconds = null)
    {
        if (db is null)
        {
            return;
        }

        string prefixed = PrefixKey(key);
        if (ttlSeconds.HasValue)
        {
            await db.StringSetAsync(prefixed, value, TimeSpan.FromSeconds(ttlSeconds.Value));
        }
        else
        {
            await db.StringSetAsync(prefixed, value);
        }
    }

    public async Task DeleteAsync(string key)
    {
        if (db is null)
        {
            return;
        }

        await db.KeyDeleteAsync(PrefixKey(key));
    }

    public async Task HashSetAsync(string key, string field, string value)
    {
        if (db is null)
        {
            return;
        }

        await db.HashSetAsync(PrefixKey(key), field, value);
    }

    public async Task<string?> HashGetAsync(string key, string field)
    {
        if (db is null)
        {
            return null;
        }

        RedisValue value = await db.HashGetAsync(PrefixKey(key), field);
        return value.IsNullOrEmpty ? null : value.ToString();
    }

    public async Task<Dictionary<string, string>> HashGetAllAsync(string key)
    {
        if (db is null)
        {
            return new Dictionary<string, string>();
        }

        HashEntry[] entries = await db.HashGetAllAsync(PrefixKey(key));
        return entries.ToDictionary(e => e.Name.ToString(), e => e.Value.ToString());
    }

    public async Task<long> HashIncrementAsync(string key, string field, long increment)
    {
        if (db is null)
        {
            return 0;
        }

        return await db.HashIncrementAsync(PrefixKey(key), field, increment);
    }

    public async Task ListPushAsync(string key, string value)
    {
        if (db is null)
        {
            return;
        }

        await db.ListLeftPushAsync(PrefixKey(key), value);
    }

    public async Task<string[]> ListRangeAsync(string key, long start, long endIndex)
    {
        if (db is null)
        {
            return [];
        }

        RedisValue[] values = await db.ListRangeAsync(PrefixKey(key), start, endIndex);
        return values.Select(v => v.ToString()).ToArray();
    }

    public async Task ListTrimAsync(string key, long start, long endIndex)
    {
        if (db is null)
        {
            return;
        }

        await db.ListTrimAsync(PrefixKey(key), start, endIndex);
    }

    public async Task<long> ListLengthAsync(string key)
    {
        if (db is null)
        {
            return 0;
        }

        return await db.ListLengthAsync(PrefixKey(key));
    }

    public async Task ExpireAsync(string key, int seconds)
    {
        if (db is null)
        {
            return;
        }

        await db.KeyExpireAsync(PrefixKey(key), TimeSpan.FromSeconds(seconds));
    }

    public async Task PublishAsync(string channel, string message)
    {
        if (subscriber is null)
        {
            return;
        }

        await subscriber.PublishAsync(RedisChannel.Literal(channel), message);
    }

    public async Task SubscribeAsync(string channel, Action<string> callback)
    {
        if (subscriber is null)
        {
            return;
        }

        await subscriber.SubscribeAsync(RedisChannel.Literal(channel), (_, value) =>
        {
            callback(value.ToString());
        });
    }

    public async Task<bool> PingAsync()
    {
        try
        {
            if (db is null)
            {
                return false;
            }

            TimeSpan result = await db.PingAsync();
            return result.TotalMilliseconds >= 0;
        }
        catch
        {
            return false;
        }
    }

    public void Disconnect()
    {
        connection?.Dispose();
        logger.LogInformation("Redis disconnected");
    }

    public void Dispose()
    {
        if (!disposed)
        {
            Disconnect();
            disposed = true;
        }

        GC.SuppressFinalize(this);
    }

    private string PrefixKey(string key) => $"{keyPrefix}{key}";
}
