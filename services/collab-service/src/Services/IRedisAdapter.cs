namespace OtterWorks.CollabService.Services;

public interface IRedisAdapter
{
    Task<byte[]?> GetAsync(string key);

    Task SetAsync(string key, byte[] value, int? ttlSeconds = null);

    Task DeleteAsync(string key);

    Task HashSetAsync(string key, string field, string value);

    Task<string?> HashGetAsync(string key, string field);

    Task<Dictionary<string, string>> HashGetAllAsync(string key);

    Task<long> HashIncrementAsync(string key, string field, long increment);

    Task ListPushAsync(string key, string value);

    Task<string[]> ListRangeAsync(string key, long start, long endIndex);

    Task ListTrimAsync(string key, long start, long endIndex);

    Task<long> ListLengthAsync(string key);

    Task ExpireAsync(string key, int seconds);

    Task PublishAsync(string channel, string message);

    Task SubscribeAsync(string channel, Action<string> callback);

    Task<bool> PingAsync();

    Task ConnectAsync();

    void Disconnect();
}
