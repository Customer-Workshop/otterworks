package com.otterworks.report.archive;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

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
