using System.Data.Common;
using Microsoft.Data.SqlClient;

namespace OtterWorks.AuditService.Archive;

/// <summary>Reads arch.FILEAUD, rebuilding TIMESTAMP(12) text from DATETIME2(7) + EVENT_TS_NANOS_TAIL.</summary>
public sealed class AzureSqlArchiveEventStore : AdoArchiveEventStore
{
    public const string Sql =
        "SELECT F.AUDIT_KEY, F.ARCH_KEY, F.EVENT_TYPE, F.EVENT_TS, F.EVENT_TS_NANOS_TAIL, F.ACTOR_ID, " +
        "F.RETENTION_CLASS, F.DISPOSITION_CODE, F.CLIENT_IP, F.DETAIL_TEXT " +
        "FROM arch.DOCARCH D LEFT JOIN arch.FILEAUD F ON F.ARCH_KEY = D.ARCH_KEY " +
        "WHERE RTRIM(D.DOC_ID) = RTRIM(@docId) ORDER BY F.EVENT_TS, F.EVENT_TS_NANOS_TAIL, F.AUDIT_KEY";

    private readonly string _connectionString;

    public AzureSqlArchiveEventStore(string connectionString)
    {
        _connectionString = connectionString;
    }

    public override string StoreName => "azuresql";

    protected override string EventsSql => Sql;

    protected override string PingSql => "SELECT 1";

    protected override DbConnection CreateConnection() => new SqlConnection(_connectionString);

    protected override ArchiveEventRow MapRow(DbDataReader reader) => MapEvent(reader);

    public static ArchiveEventRow MapEvent(DbDataReader reader)
    {
        var auditKey = Str(reader, "AUDIT_KEY");
        var archKey = Str(reader, "ARCH_KEY");
        var ts = reader.GetDateTime(reader.GetOrdinal("EVENT_TS"));
        var tail = reader.GetInt32(reader.GetOrdinal("EVENT_TS_NANOS_TAIL"));
        return new ArchiveEventRow
        {
            AuditKey = Db2Text.RTrim(auditKey),
            ArchKey = Db2Text.RTrim(archKey),
            EventType = Db2Text.RTrim(Str(reader, "EVENT_TYPE")),
            EventTs = Db2Text.Timestamp12(ts, tail),
            ActorId = Db2Text.RTrim(Str(reader, "ACTOR_ID")),
            RetentionClass = Db2Text.RTrim(Str(reader, "RETENTION_CLASS")),
            DispositionCode = Db2Text.RTrim(Str(reader, "DISPOSITION_CODE")),
            ClientIp = Db2Text.RTrim(Str(reader, "CLIENT_IP")),
            DetailText = Db2Text.RTrim(Str(reader, "DETAIL_TEXT")),
            Raw = new ArchiveEventRaw { AuditKey = auditKey, ArchKey = archKey },
        };
    }
}
