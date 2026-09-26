package com.otterworks.report.archive;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import javax.sql.DataSource;

/**
 * Resolves the {@link ArchiveStore} selected by {@code ARCHIVE_STORE} at startup.
 *
 * The service always starts: with the feature off, {@link #store()} throws
 * {@link ArchiveFeatureDisabledException} (404 + hint); with an unknown value or missing
 * connection settings the problem is logged once and {@link #store()} throws
 * {@link ArchiveStoreUnavailableException} (503).
 */
public class ArchiveStoreRegistry {

    private static final Logger logger = LoggerFactory.getLogger(ArchiveStoreRegistry.class);

    private final ArchiveStoreType type;
    private final String namespace;
    private final ArchiveStore store;
    private final JdbcTemplate migrationJdbc;
    private final String configurationError;

    public ArchiveStoreRegistry(ArchiveProperties properties) {
        this(properties, new DataSourceFactory());
    }

    ArchiveStoreRegistry(ArchiveProperties properties, DataSourceFactory dataSources) {
        this.type = properties.storeType();
        this.namespace = properties.getNamespace();
        ArchiveStore resolved = null;
        JdbcTemplate ledger = null;
        String error = null;
        switch (type) {
            case OFF:
                break;
            case DB2:
                if (properties.getDb2().isComplete()) {
                    resolved = new Db2ArchiveStore(new JdbcTemplate(dataSources.db2(properties.getDb2())));
                } else {
                    error = "ARCHIVE_STORE=db2 but DB2_HOST/DB2_DATABASE/DB2_USER/DB2_PASSWORD are incomplete";
                }
                break;
            case POSTGRESQL:
                if (properties.getPg().isComplete()) {
                    ledger = new JdbcTemplate(dataSources.pg(properties.getPg()));
                    resolved = new PostgresArchiveStore(ledger);
                } else {
                    error = "ARCHIVE_STORE=postgresql but PG_HOST/PG_DATABASE/PG_USER/PG_PASSWORD are incomplete";
                }
                break;
            case AZURESQL:
                if (properties.getAzsql().isComplete()) {
                    ledger = new JdbcTemplate(dataSources.azsql(properties.getAzsql()));
                    resolved = new AzureSqlArchiveStore(ledger);
                } else {
                    error = "ARCHIVE_STORE=azuresql but AZSQL_SERVER/AZSQL_DATABASE/AZSQL_USER/AZSQL_PASSWORD "
                            + "are incomplete";
                }
                break;
            default:
                error = "ARCHIVE_STORE has an unsupported value '" + properties.getStore()
                        + "' (expected db2, postgresql or azuresql)";
                break;
        }
        this.store = resolved;
        this.migrationJdbc = ledger;
        this.configurationError = error;
        if (error != null) {
            logger.error("archive store misconfigured: {}", error);
        } else if (resolved != null) {
            logger.info("archive store enabled: {} (namespace {})", resolved.storeName(), namespace);
        }
    }

    public ArchiveStoreType type() {
        return type;
    }

    public String namespace() {
        return namespace;
    }

    public boolean isEnabled() {
        return type != ArchiveStoreType.OFF;
    }

    public boolean isConfigured() {
        return store != null;
    }

    public String configurationError() {
        return configurationError;
    }

    /** JDBC access to the {@code mig.*} ledger; present when the store is postgresql or azuresql. */
    public JdbcTemplate migrationJdbc() {
        return migrationJdbc;
    }

    /** The selected store, or the exception that the endpoints translate into 404 / 503. */
    public ArchiveStore store() {
        if (type == ArchiveStoreType.OFF) {
            throw new ArchiveFeatureDisabledException();
        }
        if (store == null) {
            throw new ArchiveStoreUnavailableException(configurationError);
        }
        return store;
    }

    /** Builds plain (non-pooled) data sources; the archive read path is low volume. */
    public static class DataSourceFactory {

        public DataSource db2(ArchiveProperties.Db2 db2) {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("com.ibm.db2.jcc.DB2Driver");
            ds.setUrl(db2.jdbcUrl());
            ds.setUsername(db2.getUser());
            ds.setPassword(db2.getPassword());
            return ds;
        }

        public DataSource pg(ArchiveProperties.Pg pg) {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.postgresql.Driver");
            ds.setUrl(pg.jdbcUrl());
            ds.setUsername(pg.getUser());
            ds.setPassword(pg.getPassword());
            return ds;
        }

        public DataSource azsql(ArchiveProperties.Azsql azsql) {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("com.microsoft.sqlserver.jdbc.SQLServerDriver");
            ds.setUrl(azsql.jdbcUrl());
            if (!azsql.isManagedIdentity()) {
                ds.setUsername(azsql.getUser());
                ds.setPassword(azsql.getPassword());
            }
            return ds;
        }
    }
}
