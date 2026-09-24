using System.Text.Json.Serialization;

namespace OtterWorks.AuditService.Archive;

/// <summary>
/// One FILEAUD row in the wire shape shared with report-service (CONTRACTS §10.4):
/// display values are right-trimmed, timestamps are Db2 TIMESTAMP(12) text.
/// </summary>
public sealed class ArchiveEventRow
{
    [JsonPropertyName("audit_key")]
    public string AuditKey { get; set; } = string.Empty;

    [JsonPropertyName("arch_key")]
    public string ArchKey { get; set; } = string.Empty;

    [JsonPropertyName("event_type")]
    public string EventType { get; set; } = string.Empty;

    [JsonPropertyName("event_ts")]
    public string EventTs { get; set; } = string.Empty;

    [JsonPropertyName("actor_id")]
    public string ActorId { get; set; } = string.Empty;

    [JsonPropertyName("retention_class")]
    public string RetentionClass { get; set; } = string.Empty;

    [JsonPropertyName("disposition_code")]
    public string DispositionCode { get; set; } = string.Empty;

    [JsonPropertyName("client_ip")]
    public string ClientIp { get; set; } = string.Empty;

    [JsonPropertyName("detail_text")]
    public string DetailText { get; set; } = string.Empty;

    /// <summary>Key columns exactly as stored (padding preserved) for hash comparisons.</summary>
    [JsonPropertyName("raw")]
    public ArchiveEventRaw Raw { get; set; } = new();
}

public sealed class ArchiveEventRaw
{
    [JsonPropertyName("audit_key")]
    public string AuditKey { get; set; } = string.Empty;

    [JsonPropertyName("arch_key")]
    public string ArchKey { get; set; } = string.Empty;
}

public sealed class ArchiveEventsResponse
{
    [JsonPropertyName("doc_id")]
    public string DocId { get; set; } = string.Empty;

    [JsonPropertyName("store")]
    public string Store { get; set; } = string.Empty;

    [JsonPropertyName("events")]
    public IReadOnlyList<ArchiveEventRow> Events { get; set; } = Array.Empty<ArchiveEventRow>();
}
