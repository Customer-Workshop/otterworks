namespace OtterWorks.AuditService.Archive;

public interface IArchiveEventStore
{
    /// <summary><c>db2</c>, <c>postgresql</c> or <c>azuresql</c>.</summary>
    string StoreName { get; }

    /// <summary>
    /// FILEAUD events for every DOCARCH version of <paramref name="docId"/>, ordered by
    /// EVENT_TS then AUDIT_KEY. Null when the document has no versions in this store.
    /// </summary>
    Task<IReadOnlyList<ArchiveEventRow>?> GetEventsAsync(string docId, CancellationToken cancellationToken);

    /// <summary>
    /// DOCARCH versions of <paramref name="docId"/> ordered by VERSION_NO, each with its FILEAUD
    /// events (CONTRACTS §10.4). Null when the document has no versions in this store.
    /// </summary>
    Task<IReadOnlyList<ArchiveVersionRow>?> GetDocumentAsync(string docId, CancellationToken cancellationToken);

    Task PingAsync(CancellationToken cancellationToken);
}

public sealed class ArchiveFeatureDisabledException : Exception
{
    public const string Hint = "archive feature is off; set ARCHIVE_STORE=db2, postgresql or azuresql to enable it";

    public ArchiveFeatureDisabledException() : base(Hint)
    {
    }
}

public sealed class ArchiveStoreUnavailableException : Exception
{
    public ArchiveStoreUnavailableException(string message, Exception? inner = null) : base(message, inner)
    {
    }
}
