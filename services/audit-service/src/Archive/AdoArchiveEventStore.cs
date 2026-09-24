using System.Data;
using System.Data.Common;

namespace OtterWorks.AuditService.Archive;

/// <summary>
/// Provider-neutral assembly of the FILEAUD read: subclasses supply the connection, the SQL
/// (never trimming CHAR columns in SQL) and the row mapping.
/// </summary>
public abstract class AdoArchiveEventStore : IArchiveEventStore
{
    public abstract string StoreName { get; }

    protected abstract DbConnection CreateConnection();

    protected abstract string EventsSql { get; }

    protected abstract string PingSql { get; }

    protected abstract ArchiveEventRow MapRow(DbDataReader reader);

    public async Task<IReadOnlyList<ArchiveEventRow>?> GetEventsAsync(string docId, CancellationToken cancellationToken)
    {
        try
        {
            await using var connection = CreateConnection();
            await connection.OpenAsync(cancellationToken);
            await using var command = connection.CreateCommand();
            command.CommandText = EventsSql;
            var parameter = command.CreateParameter();
            parameter.ParameterName = "@docId";
            parameter.DbType = DbType.String;
            parameter.Value = docId;
            command.Parameters.Add(parameter);

            var rows = new List<ArchiveEventRow>();
            var anyVersion = false;
            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                anyVersion = true;
                if (await reader.IsDBNullAsync("AUDIT_KEY", cancellationToken))
                {
                    continue;
                }

                rows.Add(MapRow(reader));
            }

            return anyVersion ? rows : null;
        }
        catch (DbException ex)
        {
            throw new ArchiveStoreUnavailableException($"{StoreName} archive query failed: {ex.Message}", ex);
        }
    }

    public async Task PingAsync(CancellationToken cancellationToken)
    {
        try
        {
            await using var connection = CreateConnection();
            await connection.OpenAsync(cancellationToken);
            await using var command = connection.CreateCommand();
            command.CommandText = PingSql;
            await command.ExecuteScalarAsync(cancellationToken);
        }
        catch (DbException ex)
        {
            throw new ArchiveStoreUnavailableException($"{StoreName} archive store unreachable: {ex.Message}", ex);
        }
    }

    protected static string Str(DbDataReader reader, string column) =>
        reader.IsDBNull(reader.GetOrdinal(column)) ? string.Empty : reader.GetString(reader.GetOrdinal(column));
}
