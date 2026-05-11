namespace OtterWorks.DocumentService.Services;

public interface IEventPublisher
{
    Task PublishAsync(string eventType, Dictionary<string, object> payload);
}
