namespace OtterWorks.AuditService.Archive;

/// <summary>
/// Picks the store from ARCHIVE_STORE at startup. Missing or invalid settings never stop the
/// service: they are logged once and surface as 503 on the archive endpoints only.
/// </summary>
public sealed class ArchiveStoreRegistry
{
    private readonly IArchiveEventStore? _store;

    public ArchiveStoreRegistry(ArchiveStoreOptions options, ILogger<ArchiveStoreRegistry> logger)
        : this(options, logger, CreateStore)
    {
    }

    public ArchiveStoreRegistry(
        ArchiveStoreOptions options,
        ILogger<ArchiveStoreRegistry> logger,
        Func<ArchiveStoreOptions, IArchiveEventStore> factory)
    {
        Type = options.StoreType;
        Namespace = options.Namespace;
        switch (Type)
        {
            case ArchiveStoreType.Off:
                break;
            case ArchiveStoreType.Db2 when !options.Db2Complete:
                ConfigurationError = "ARCHIVE_STORE=db2 but DB2_HOST/DB2_DATABASE/DB2_USER/DB2_PASSWORD are incomplete";
                break;
            case ArchiveStoreType.PostgreSql when !options.PgComplete:
                ConfigurationError = "ARCHIVE_STORE=postgresql but PG_HOST/PG_DATABASE/PG_USER/PG_PASSWORD are incomplete";
                break;
            case ArchiveStoreType.AzureSql when !options.AzsqlComplete:
                ConfigurationError = "ARCHIVE_STORE=azuresql but AZSQL_SERVER/AZSQL_DATABASE/AZSQL_USER/AZSQL_PASSWORD are incomplete";
                break;
            case ArchiveStoreType.Invalid:
                ConfigurationError = $"ARCHIVE_STORE has an unsupported value '{options.Store}' (expected db2, postgresql or azuresql)";
                break;
            default:
                _store = factory(options);
                break;
        }

        if (ConfigurationError is not null)
        {
            logger.LogError("archive store misconfigured: {Error}", ConfigurationError);
        }
    }

    public ArchiveStoreType Type { get; }

    public string Namespace { get; }

    public string? ConfigurationError { get; }

    public IArchiveEventStore Store =>
        Type == ArchiveStoreType.Off
            ? throw new ArchiveFeatureDisabledException()
            : _store ?? throw new ArchiveStoreUnavailableException(ConfigurationError ?? "archive store not configured");

    private static IArchiveEventStore CreateStore(ArchiveStoreOptions options) => options.StoreType switch
    {
        ArchiveStoreType.Db2 => new Db2ArchiveEventStore(options.Db2ConnectionString),
        ArchiveStoreType.PostgreSql => new PostgresArchiveEventStore(options.PgConnectionString),
        ArchiveStoreType.AzureSql => new AzureSqlArchiveEventStore(options.AzsqlConnectionString),
        _ => throw new InvalidOperationException("no store for " + options.StoreType),
    };
}
