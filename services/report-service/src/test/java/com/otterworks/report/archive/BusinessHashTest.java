package com.otterworks.report.archive;

import com.otterworks.report.archive.ArchiveDocument.ArchiveEvent;
import com.otterworks.report.archive.ArchiveDocument.ArchiveVersion;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

public class BusinessHashTest {

    static ArchiveVersion version(String rawArchKey) {
        ArchiveVersion v = new ArchiveVersion();
        v.raw.archKey = rawArchKey;
        v.raw.docId = "0F2A1B3C-0000-4000-8000-000000000042  ";
        v.raw.legalHoldFlag = "N";
        v.raw.dispositionDt = "20230301";
        v.archKey = Db2Text.rtrim(rawArchKey);
        v.versionNo = 3;
        v.retentionClass = "FIN7";
        v.lastAccessTs = "2016-03-01-10.15.30.123456789012";
        v.storageCharge = "1234.50000000";
        v.unitRate = "0.01000000";
        v.ownerName = "LOPEZ, M.";
        v.dispositionDt = "2023-03-01";
        v.contentSha256 = "AB".concat(new String(new char[62]).replace('\0', '0'));
        v.byteSize = 4096;
        return v;
    }

    @Test
    public void docarchHashIsDeterministicAndKnown() {
        String expected = BusinessHash.sha256Hex("DA00000000000042|0F2A1B3C-0000-4000-8000-000000000042|3|FIN7|"
                + "2016-03-01-10.15.30.123456789012|1234.50000000|0.01000000|LOPEZ, M.|20230301|N|"
                + "AB" + new String(new char[62]).replace('\0', '0') + "|4096");
        assertEquals(expected, BusinessHash.docarch(version("DA00000000000042")));
        assertEquals(64, expected.length());
    }

    @Test
    public void paddedKeyChangesTheHashLikeMig04() {
        assertNotEquals(BusinessHash.docarch(version("DA00000000000042")),
                BusinessHash.docarch(version("DA00000000000042  ")));
    }

    @Test
    public void fileaudHashUsesManifestOrder() {
        ArchiveEvent e = new ArchiveEvent();
        e.raw.auditKey = "FA000000000000000123";
        e.raw.archKey = "DA00000000000042";
        e.eventType = "VIEW";
        e.eventTs = "2015-07-02-08.00.00.000000000001";
        e.actorId = "U00000000042";
        e.retentionClass = "FIN7";
        e.dispositionCode = "00";
        e.clientIp = "10.1.2.3";
        e.detailText = "VIEW v3";
        String expected = BusinessHash.sha256Hex("FA000000000000000123|DA00000000000042|VIEW|"
                + "2015-07-02-08.00.00.000000000001|U00000000042|FIN7|00|10.1.2.3|VIEW v3");
        assertEquals(expected, BusinessHash.fileaud(e));
    }
}
