using System.Data.Common;
using System.Globalization;
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

    public const string VersionsSqlText =
        "SELECT ARCH_KEY, DOC_ID, VERSION_NO, RETENTION_CLASS, LAST_ACCESS_TS, LAST_ACCESS_TS_NANOS_TAIL, " +
        "STORAGE_CHARGE, OWNER_NAME, DISPOSITION_DT, LEGAL_HOLD_FLAG " +
        "FROM arch.DOCARCH WHERE RTRIM(DOC_ID) = RTRIM(@docId) ORDER BY VERSION_NO";

    private readonly string _connectionString;

    public AzureSqlArchiveEventStore(string connectionString)
    {
        _connectionString = connectionString;
    }

    public override string StoreName => "azuresql";

    protected override string EventsSql => Sql;

    protected override string VersionsSql => VersionsSqlText;

    protected override string PingSql => "SELECT 1";

    protected override DbConnection CreateConnection() => new SqlConnection(_connectionString);

    protected override ArchiveEventRow MapRow(DbDataReader reader) => MapEvent(reader);

    protected override ArchiveVersionRow MapVersion(DbDataReader reader)
    {
        var archKey = Str(reader, "ARCH_KEY");
        var docId = Str(reader, "DOC_ID");
        var ts = reader.GetDateTime(reader.GetOrdinal("LAST_ACCESS_TS"));
        var tail = reader.GetInt32(reader.GetOrdinal("LAST_ACCESS_TS_NANOS_TAIL"));
        var dispOrdinal = reader.GetOrdinal("DISPOSITION_DT");
        return new ArchiveVersionRow
        {
            ArchKey = Db2Text.RTrim(archKey),
            VersionNo = reader.GetInt32(reader.GetOrdinal("VERSION_NO")),
            RetentionClass = Db2Text.RTrim(Str(reader, "RETENTION_CLASS")),
            LastAccessTs = Db2Text.Timestamp12(ts, tail),
            StorageCharge = Db2Text.Decimal8(reader.GetDecimal(reader.GetOrdinal("STORAGE_CHARGE"))),
            OwnerName = Db2Text.RTrim(Str(reader, "OWNER_NAME")),
            DispositionDt = reader.IsDBNull(dispOrdinal)
                ? string.Empty
                : reader.GetDateTime(dispOrdinal).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
            LegalHold = Db2Text.RTrim(Str(reader, "LEGAL_HOLD_FLAG")) == "Y",
            Raw = new ArchiveVersionRaw { ArchKey = archKey, DocId = docId },
        };
    }

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
