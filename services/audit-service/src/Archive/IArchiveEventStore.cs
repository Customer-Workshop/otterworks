namespace OtterWorks.AuditService.Archive;

public interface IArchiveEventStore
{
    /// <summary><c>db2</c> or <c>azuresql</c>.</summary>
    string StoreName { get; }

    /// <summary>
    /// FILEAUD events for every DOCARCH version of <paramref name="docId"/>, ordered by
    /// EVENT_TS then AUDIT_KEY. Null when the document has no versions in this store.
    /// </summary>
    Task<IReadOnlyList<ArchiveEventRow>?> GetEventsAsync(string docId, CancellationToken cancellationToken);

    Task PingAsync(CancellationToken cancellationToken);
}

public sealed class ArchiveFeatureDisabledException : Exception
{
    public const string Hint = "archive feature is off; set ARCHIVE_STORE=db2 or ARCHIVE_STORE=azuresql to enable it";

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
