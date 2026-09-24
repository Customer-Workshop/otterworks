using System.Text.Json.Serialization;

namespace OtterWorks.AuditService.Archive;

/// <summary>One DOCARCH version with its FILEAUD events (CONTRACTS §10.4 wire shape).</summary>
public sealed class ArchiveVersionRow
{
    [JsonPropertyName("arch_key")]
    public string ArchKey { get; set; } = string.Empty;

    [JsonPropertyName("version_no")]
    public int VersionNo { get; set; }

    [JsonPropertyName("retention_class")]
    public string RetentionClass { get; set; } = string.Empty;

    [JsonPropertyName("last_access_ts")]
    public string LastAccessTs { get; set; } = string.Empty;

    [JsonPropertyName("storage_charge")]
    public string StorageCharge { get; set; } = string.Empty;

    [JsonPropertyName("owner_name")]
    public string OwnerName { get; set; } = string.Empty;

    [JsonPropertyName("disposition_dt")]
    public string DispositionDt { get; set; } = string.Empty;

    [JsonPropertyName("legal_hold")]
    public bool LegalHold { get; set; }

    [JsonPropertyName("events")]
    public List<ArchiveEventRow> Events { get; set; } = new();

    /// <summary>Key exactly as stored (padding preserved).</summary>
    [JsonPropertyName("raw")]
    public ArchiveVersionRaw Raw { get; set; } = new();
}

public sealed class ArchiveVersionRaw
{
    [JsonPropertyName("arch_key")]
    public string ArchKey { get; set; } = string.Empty;

    [JsonPropertyName("doc_id")]
    public string DocId { get; set; } = string.Empty;
}

public sealed class ArchiveDocumentResponse
{
    [JsonPropertyName("doc_id")]
    public string DocId { get; set; } = string.Empty;

    [JsonPropertyName("store")]
    public string Store { get; set; } = string.Empty;

    [JsonPropertyName("versions")]
    public IReadOnlyList<ArchiveVersionRow> Versions { get; set; } = Array.Empty<ArchiveVersionRow>();
}
