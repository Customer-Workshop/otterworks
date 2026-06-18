package com.otterworks.report.service.ehr;

import com.otterworks.report.model.ehr.Ehr;
import com.otterworks.report.repository.ehr.EhrRepository;
import org.junit.Before;
import org.junit.Test;
import org.mockito.Mockito;

import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.UUID;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.mockito.Mockito.when;

public class EhrServiceImplTest {

    private EhrRepository ehrRepository;
    private EhrServiceImpl ehrService;

    @Before
    public void setUp() {
        ehrRepository = Mockito.mock(EhrRepository.class);
        ehrService = new EhrServiceImpl(ehrRepository);
    }

    @Test
    public void isQueryableReturnsTrueForQueryableEhr() {
        UUID ehrId = UUID.randomUUID();
        when(ehrRepository.fetchIsQueryable(ehrId)).thenReturn(true);

        assertTrue(ehrService.isQueryable(ehrId));
    }

    @Test
    public void isQueryableReturnsFalseForNonQueryableEhr() {
        UUID ehrId = UUID.randomUUID();
        when(ehrRepository.fetchIsQueryable(ehrId)).thenReturn(false);

        assertFalse(ehrService.isQueryable(ehrId));
    }

    @Test
    public void isQueryableReturnsFalseWhenEhrNotFound() {
        UUID ehrId = UUID.randomUUID();
        when(ehrRepository.fetchIsQueryable(ehrId)).thenReturn(null);

        assertFalse(ehrService.isQueryable(ehrId));
    }

    @Test
    public void getQueryableEhrIdsReturnsOnlyQueryableEhrs() {
        UUID ehr1 = UUID.randomUUID();
        UUID ehr2 = UUID.randomUUID();

        Ehr e1 = new Ehr();
        e1.setEhrId(ehr1);
        e1.setPatientId("patient-1");
        e1.setQueryable(true);
        e1.setCreatedAt(new Date());

        Ehr e2 = new Ehr();
        e2.setEhrId(ehr2);
        e2.setPatientId("patient-1");
        e2.setQueryable(true);
        e2.setCreatedAt(new Date());

        when(ehrRepository.findByPatientIdAndQueryableTrue("patient-1"))
                .thenReturn(Arrays.asList(e1, e2));

        List<UUID> ids = ehrService.getQueryableEhrIds("patient-1");

        assertEquals(2, ids.size());
        assertTrue(ids.contains(ehr1));
        assertTrue(ids.contains(ehr2));
    }

    @Test
    public void getQueryableEhrIdsReturnsEmptyForUnknownPatient() {
        when(ehrRepository.findByPatientIdAndQueryableTrue("unknown"))
                .thenReturn(Collections.<Ehr>emptyList());

        List<UUID> ids = ehrService.getQueryableEhrIds("unknown");

        assertTrue(ids.isEmpty());
    }

    @Test
    public void nonQueryableEhrReturnsNoData() {
        when(ehrRepository.findByPatientIdAndQueryableTrue("patient-nonq"))
                .thenReturn(Collections.<Ehr>emptyList());

        List<UUID> ids = ehrService.getQueryableEhrIds("patient-nonq");
        assertTrue(ids.isEmpty());
    }
}
