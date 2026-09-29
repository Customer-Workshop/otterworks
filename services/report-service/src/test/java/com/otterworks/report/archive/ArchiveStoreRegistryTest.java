package com.otterworks.report.archive;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class ArchiveStoreRegistryTest {

    @Test
    public void unsetStoreMeansFeatureOff() {
        ArchiveStoreRegistry registry = new ArchiveStoreRegistry(new ArchiveProperties());
        assertEquals(ArchiveStoreType.OFF, registry.type());
        assertFalse(registry.isEnabled());
        try {
            registry.store();
            fail("expected feature-off exception");
        } catch (ArchiveFeatureDisabledException e) {
            assertTrue(e.getMessage().contains("ARCHIVE_STORE=db2"));
        }
    }

    @Test
    public void unknownValueStartsButIsUnavailable() {
        ArchiveProperties props = new ArchiveProperties();
        props.setStore("oracle");
        ArchiveStoreRegistry registry = new ArchiveStoreRegistry(props);
        assertEquals(ArchiveStoreType.INVALID, registry.type());
        assertTrue(registry.isEnabled());
        assertFalse(registry.isConfigured());
        try {
            registry.store();
            fail("expected unavailable exception");
        } catch (ArchiveStoreUnavailableException e) {
            assertTrue(e.getMessage().contains("oracle"));
        }
    }

    @Test
    public void db2WithoutConnectionVarsIsUnavailable() {
        ArchiveProperties props = new ArchiveProperties();
        props.setStore("db2");
        props.getDb2().setHost("db2.example");
        ArchiveStoreRegistry registry = new ArchiveStoreRegistry(props);
        assertFalse(registry.isConfigured());
        assertTrue(registry.configurationError().contains("DB2_"));
        assertNull(registry.migrationJdbc());
    }

    @Test
    public void completeAzureSqlSettingsBuildTheStoreWithoutConnecting() {
        ArchiveProperties props = new ArchiveProperties();
        props.setStore("AzureSQL");
        props.setNamespace("x1-after");
        props.getAzsql().setServer("sql-x1-after.database.windows.net");
        props.getAzsql().setDatabase("otterworks_x1_after");
        props.getAzsql().setUser("reader");
        props.getAzsql().setPassword("secret");
        ArchiveStoreRegistry registry = new ArchiveStoreRegistry(props);
        assertEquals(ArchiveStoreType.AZURESQL, registry.type());
        assertTrue(registry.isConfigured());
        assertEquals("azuresql", registry.store().storeName());
        assertEquals("x1-after", registry.namespace());
        assertTrue(props.getAzsql().jdbcUrl().startsWith("jdbc:sqlserver://sql-x1-after.database.windows.net:1433;"));
        assertTrue(props.getAzsql().jdbcUrl().contains("encrypt=true"));
    }

    @Test
    public void completePostgresSettingsBuildTheStoreAndLedgerWithoutConnecting() {
        ArchiveProperties props = new ArchiveProperties();
        props.setStore("postgresql");
        props.setNamespace("x1-after");
        props.getPg().setHost("otterworks-dev.cluster.us-east-1.rds.amazonaws.com");
        props.getPg().setDatabase("otterworks_x1");
        props.getPg().setUser("reader");
        props.getPg().setPassword("secret");
        props.getPg().setSslmode("require");
        ArchiveStoreRegistry registry = new ArchiveStoreRegistry(props);
        assertEquals(ArchiveStoreType.POSTGRESQL, registry.type());
        assertTrue(registry.isConfigured());
        assertEquals("postgresql", registry.store().storeName());
        assertTrue(registry.migrationJdbc() != null);
        assertTrue(ArchiveStoreType.POSTGRESQL.hasMigrationLedger());
        assertFalse(ArchiveStoreType.DB2.hasMigrationLedger());
        assertEquals("jdbc:postgresql://otterworks-dev.cluster.us-east-1.rds.amazonaws.com:5432/otterworks_x1"
                + "?sslmode=require", props.getPg().jdbcUrl());
    }

    @Test
    public void postgresWithoutConnectionVarsIsUnavailable() {
        ArchiveProperties props = new ArchiveProperties();
        props.setStore("postgres");
        props.getPg().setHost("pg.example");
        ArchiveStoreRegistry registry = new ArchiveStoreRegistry(props);
        assertEquals(ArchiveStoreType.POSTGRESQL, registry.type());
        assertFalse(registry.isConfigured());
        assertTrue(registry.configurationError().contains("PG_"));
        assertNull(registry.migrationJdbc());
    }

    @Test
    public void completeDb2SettingsBuildTheStore() {
        ArchiveProperties props = new ArchiveProperties();
        props.setStore("db2");
        props.getDb2().setHost("db2-0.db2");
        props.getDb2().setDatabase("D24BEF");
        props.getDb2().setUser("archrd");
        props.getDb2().setPassword("secret");
        ArchiveStoreRegistry registry = new ArchiveStoreRegistry(props);
        assertEquals("db2", registry.store().storeName());
        assertEquals("jdbc:db2://db2-0.db2:50000/D24BEF", props.getDb2().jdbcUrl());
    }
}
