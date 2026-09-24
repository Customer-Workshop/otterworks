using System.Data.Common;
using IBM.Data.Db2;

namespace OtterWorks.AuditService.Archive;

/// <summary>Reads ARCHIVE.FILEAUD through the Db2 .NET provider; CHAR padding survives to the DTO.</summary>
public sealed class Db2ArchiveEventStore : AdoArchiveEventStore
{
    // LEFT JOIN so a document with versions but no events is distinguishable from an unknown document.
    public const string Sql =
        "SELECT F.AUDIT_KEY, F.ARCH_KEY, F.EVENT_TYPE, CHAR(F.EVENT_TS) AS EVENT_TS, F.ACTOR_ID, " +
        "F.RETENTION_CLASS, F.DISPOSITION_CODE, F.CLIENT_IP, F.DETAIL_TEXT " +
        "FROM ARCHIVE.DOCARCH D LEFT JOIN ARCHIVE.FILEAUD F ON F.ARCH_KEY = D.ARCH_KEY " +
        "WHERE D.DOC_ID = @docId ORDER BY F.EVENT_TS, F.AUDIT_KEY";

    private readonly string _connectionString;

    public Db2ArchiveEventStore(string connectionString)
    {
        _connectionString = connectionString;
    }

    public override string StoreName => "db2";

    protected override string EventsSql => Sql;

    protected override string PingSql => "SELECT 1 FROM SYSIBM.SYSDUMMY1";

    protected override DbConnection CreateConnection() => new DB2Connection(_connectionString);

    protected override ArchiveEventRow MapRow(DbDataReader reader) => MapEvent(reader);

    public static ArchiveEventRow MapEvent(DbDataReader reader)
    {
        var auditKey = Str(reader, "AUDIT_KEY");
        var archKey = Str(reader, "ARCH_KEY");
        return new ArchiveEventRow
        {
            AuditKey = Db2Text.RTrim(auditKey),
            ArchKey = Db2Text.RTrim(archKey),
            EventType = Db2Text.RTrim(Str(reader, "EVENT_TYPE")),
            EventTs = Db2Text.Timestamp12(Str(reader, "EVENT_TS")),
            ActorId = Db2Text.RTrim(Str(reader, "ACTOR_ID")),
            RetentionClass = Db2Text.RTrim(Str(reader, "RETENTION_CLASS")),
            DispositionCode = Db2Text.RTrim(Str(reader, "DISPOSITION_CODE")),
            ClientIp = Db2Text.RTrim(Str(reader, "CLIENT_IP")),
            DetailText = Db2Text.RTrim(Str(reader, "DETAIL_TEXT")),
            Raw = new ArchiveEventRaw { AuditKey = auditKey, ArchKey = archKey },
        };
    }
}
