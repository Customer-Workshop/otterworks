package com.otterworks.report.archive;

import com.otterworks.report.archive.ArchiveDocument.ArchiveEvent;
import com.otterworks.report.archive.ArchiveDocument.ArchiveVersion;
import org.junit.Before;
import org.junit.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.Collections;
import java.util.Optional;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

public class ArchiveControllerTest {

    private ArchiveStore store;
    private MockMvc mvc;

    @Before
    public void setUp() {
        store = mock(ArchiveStore.class);
        when(store.storeName()).thenReturn("db2");
    }

    private MockMvc mvcFor(ArchiveStoreRegistry registry) {
        return MockMvcBuilders.standaloneSetup(new ArchiveController(registry))
                .setControllerAdvice(new ArchiveExceptionHandler())
                .build();
    }

    private static ArchiveStoreRegistry registryWith(final ArchiveStore store, ArchiveStoreType type) {
        ArchiveStoreRegistry registry = mock(ArchiveStoreRegistry.class);
        when(registry.type()).thenReturn(type);
        if (type == ArchiveStoreType.OFF) {
            when(registry.store()).thenThrow(new ArchiveFeatureDisabledException());
        } else if (store == null) {
            when(registry.store())
                    .thenThrow(new ArchiveStoreUnavailableException("ARCHIVE_STORE has an unsupported value"));
        } else {
            when(registry.store()).thenReturn(store);
        }
        return registry;
    }

    @Test
    public void featureOffReturns404WithHint() throws Exception {
        mvc = mvcFor(registryWith(null, ArchiveStoreType.OFF));
        mvc.perform(get("/api/archive/documents/abc"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.hint").value(containsString("ARCHIVE_STORE=db2")));
        mvc.perform(get("/api/archive/documents/abc/hash")).andExpect(status().isNotFound());
    }

    @Test
    public void misconfiguredStoreReturns503() throws Exception {
        mvc = mvcFor(registryWith(null, ArchiveStoreType.INVALID));
        mvc.perform(get("/api/v1/archive/documents/abc"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error").value("archive store unavailable"));
    }

    @Test
    public void unknownDocumentReturns404() throws Exception {
        when(store.findDocument(anyString())).thenReturn(Optional.<ArchiveDocument>empty());
        mvc = mvcFor(registryWith(store, ArchiveStoreType.DB2));
        mvc.perform(get("/api/archive/documents/nope"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("document not found"));
    }

    @Test
    public void documentIsTrimmedAndRawOnlyOnRequest() throws Exception {
        when(store.findDocument("doc-1")).thenAnswer(invocation -> Optional.of(sample()));
        mvc = mvcFor(registryWith(store, ArchiveStoreType.DB2));
        mvc.perform(get("/api/archive/documents/doc-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.store").value("db2"))
                .andExpect(jsonPath("$.versions[0].arch_key").value("DA00000000000042"))
                .andExpect(jsonPath("$.versions[0].owner_name").value("LOPEZ, M."))
                .andExpect(jsonPath("$.versions[0].raw").doesNotExist())
                .andExpect(jsonPath("$.versions[0].events[0].raw").doesNotExist())
                .andExpect(content().string(containsString("\"last_access_ts\":\"2016-03-01-10.15.30.123456789012\"")));
        mvc.perform(get("/api/archive/documents/doc-1").param("raw", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.versions[0].raw.arch_key").value("DA00000000000042  "))
                .andExpect(jsonPath("$.versions[0].raw.owner_name").value("LOPEZ, M.                               "));
    }

    @Test
    public void hashEndpointReturnsRowAndDocumentHashes() throws Exception {
        when(store.findDocument("doc-1")).thenAnswer(invocation -> Optional.of(sample()));
        mvc = mvcFor(registryWith(store, ArchiveStoreType.DB2));
        ArchiveDocument doc = sample();
        String expectedVersion = BusinessHash.docarch(doc.getVersions().get(0));
        String expectedEvent = BusinessHash.fileaud(doc.getVersions().get(0).events.get(0));
        mvc.perform(get("/api/archive/documents/doc-1/hash"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.doc_id").value("doc-1"))
                .andExpect(jsonPath("$.versions[0].row_hash").value(expectedVersion))
                .andExpect(jsonPath("$.versions[0].events[0].row_hash").value(expectedEvent))
                .andExpect(jsonPath("$.document_hash")
                        .value(BusinessHash.sha256Hex(expectedVersion + "\n" + expectedEvent + "\n")));
    }

    static ArchiveDocument sample() {
        ArchiveVersion v = new ArchiveVersion();
        v.raw.archKey = "DA00000000000042  ";
        v.raw.docId = "doc-1";
        v.raw.retentionClass = "FIN7";
        v.raw.ownerName = "LOPEZ, M.                               ";
        v.raw.dispositionDt = "20230301";
        v.raw.legalHoldFlag = "N";
        v.archKey = "DA00000000000042";
        v.versionNo = 3;
        v.retentionClass = "FIN7";
        v.lastAccessTs = "2016-03-01-10.15.30.123456789012";
        v.storageCharge = "1234.50000000";
        v.unitRate = "0.01000000";
        v.ownerName = "LOPEZ, M.";
        v.dispositionDt = "2023-03-01";
        v.contentSha256 = "00";
        v.byteSize = 10;
        ArchiveEvent e = new ArchiveEvent();
        e.raw.auditKey = "FA000000000000000123";
        e.raw.archKey = "DA00000000000042  ";
        e.auditKey = "FA000000000000000123";
        e.eventType = "VIEW";
        e.eventTs = "2015-07-02-08.00.00.000000000001";
        e.actorId = "U00000000042";
        e.retentionClass = "FIN7";
        e.dispositionCode = "00";
        e.clientIp = "10.1.2.3";
        e.detailText = "VIEW v3";
        v.events = Collections.singletonList(e);
        return new ArchiveDocument("doc-1", "db2", Collections.singletonList(v));
    }
}
