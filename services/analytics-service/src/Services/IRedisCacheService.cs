namespace OtterWorks.AnalyticsService.Services;

public interface IRedisCacheService
{
    Task<T?> GetAsync<T>(string key)
        where T : class;

    Task SetAsync<T>(string key, T value, TimeSpan? expiry = null)
        where T : class;

    Task RemoveAsync(string key);
}
