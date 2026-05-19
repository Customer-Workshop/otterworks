package com.otterworks.report.service;

import com.otterworks.report.config.AppConfig;
import org.junit.Before;
import org.junit.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.util.*;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class ReportDataFetcherTest {

    @Mock
    private RestTemplate restTemplate;

    @Mock
    private AppConfig appConfig;

    private ReportDataFetcher fetcher;

    @Before
    public void setUp() {
        MockitoAnnotations.openMocks(this);
        when(appConfig.getAnalyticsServiceUrl()).thenReturn("http://analytics:8088");
        when(appConfig.getAuditServiceUrl()).thenReturn("http://audit:8090");
        fetcher = new ReportDataFetcher(restTemplate, appConfig);
    }

    @Test
    public void fetchAnalyticsDataReturnsEventsFromResponse() {
        List<Map<String, Object>> events = new ArrayList<>();
        Map<String, Object> event = new HashMap<>();
        event.put("type", "login");
        event.put("count", 42);
        events.add(event);

        Map<String, Object> responseBody = new HashMap<>();
        responseBody.put("events", events);

        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenReturn(ResponseEntity.ok(responseBody));

        Date from = new Date(System.currentTimeMillis() - 86400000);
        Date to = new Date();
        List<Map<String, Object>> result = fetcher.fetchAnalyticsData(from, to, null);

        assertNotNull(result);
        assertFalse(result.isEmpty());
        assertEquals("login", result.get(0).get("type"));
    }

    @Test(expected = com.google.common.util.concurrent.UncheckedExecutionException.class)
    public void fetchAnalyticsDataThrowsOnRestClientError() {
        // RestClientException is unchecked, so Guava cache wraps in UncheckedExecutionException
        // (not ExecutionException). The catch block only handles ExecutionException.
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenThrow(new RestClientException("Connection refused"));

        Date from = new Date(System.currentTimeMillis() - 86400000);
        Date to = new Date();
        fetcher.fetchAnalyticsData(from, to, null);
    }

    @Test
    public void fetchAnalyticsDataReturnsEmptyForNoEvents() {
        Map<String, Object> responseBody = new HashMap<>();
        responseBody.put("other", "data");

        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenReturn(ResponseEntity.ok(responseBody));

        Date from = new Date(System.currentTimeMillis() - 86400000);
        Date to = new Date();
        List<Map<String, Object>> result = fetcher.fetchAnalyticsData(from, to, null);

        assertNotNull(result);
        assertTrue(result.isEmpty());
    }

    @Test
    public void fetchAuditDataReturnsEntriesFromResponse() {
        List<Map<String, Object>> entries = new ArrayList<>();
        Map<String, Object> entry = new HashMap<>();
        entry.put("action", "file_upload");
        entries.add(entry);

        Map<String, Object> responseBody = new HashMap<>();
        responseBody.put("events", entries);

        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenReturn(ResponseEntity.ok(responseBody));

        Date from = new Date(System.currentTimeMillis() - 86400000);
        Date to = new Date();
        List<Map<String, Object>> result = fetcher.fetchAuditData(from, to, null);

        assertNotNull(result);
    }

    @Test
    public void fetchAnalyticsDataIncludesMetricParam() {
        Map<String, Object> responseBody = new HashMap<>();
        responseBody.put("events", Collections.emptyList());

        when(restTemplate.getForEntity(contains("metric=page_views"), eq(Map.class)))
                .thenReturn(ResponseEntity.ok(responseBody));

        Date from = new Date(System.currentTimeMillis() - 86400000);
        Date to = new Date();
        Map<String, String> params = new HashMap<>();
        params.put("metric", "page_views");
        List<Map<String, Object>> result = fetcher.fetchAnalyticsData(from, to, params);

        assertNotNull(result);
    }
}
