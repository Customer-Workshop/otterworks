using System.Text.Json.Serialization;

namespace OtterWorks.NotificationService.Models;

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum DeliveryChannel
{
    EMAIL,
    IN_APP,
    PUSH,
}
