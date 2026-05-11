using System.Text.Json.Serialization;

namespace OtterWorks.NotificationService.Models;

public class NotificationPreference
{
    [JsonPropertyName("userId")]
    public string UserId { get; set; } = string.Empty;

    [JsonPropertyName("channels")]
    public Dictionary<string, List<DeliveryChannel>> Channels { get; set; } = new()
    {
        ["file_shared"] = new List<DeliveryChannel> { DeliveryChannel.EMAIL, DeliveryChannel.IN_APP, DeliveryChannel.PUSH },
        ["comment_added"] = new List<DeliveryChannel> { DeliveryChannel.IN_APP, DeliveryChannel.PUSH },
        ["document_edited"] = new List<DeliveryChannel> { DeliveryChannel.IN_APP },
        ["user_mentioned"] = new List<DeliveryChannel> { DeliveryChannel.EMAIL, DeliveryChannel.IN_APP, DeliveryChannel.PUSH },
    };
}
