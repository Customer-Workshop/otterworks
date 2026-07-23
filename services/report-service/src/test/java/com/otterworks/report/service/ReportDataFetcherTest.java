package com.otterworks.report.service;

import com.google.common.util.concurrent.UncheckedExecutionException;
import com.otterworks.report.config.AppConfig;
import org.junit.Before;
import org.junit.Test;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Unit tests for {@link ReportDataFetcher}.
 *
 * Covers cache behavior, remote fetches via RestTemplate, and the
 * sample-data fallback used when remote services are unavailable.
 */
public class ReportDataFetcherTest {

    private RestTemplate restTemplate;
    private AppConfig appConfig;
    private ReportDataFetcher fetcher;

    private final Date dateFrom = new Date(System.currentTimeMillis() - 86400000L * 7);
    private final Date dateTo = new Date();

    @Before
    public void setUp() {
        restTemplate = mock(RestTemplate.class);
        appConfig = mock(AppConfig.class);
        when(appConfig.getAnalyticsServiceUrl()).thenReturn("http://analytics-service:8088");
        when(appConfig.getAuditServiceUrl()).thenReturn("http://audit-service:8090");
        when(appConfig.getAuthServiceUrl()).thenReturn("http://auth-service:8081");
        fetcher = new ReportDataFetcher(restTemplate, appConfig);
    }

    private ResponseEntity<Map> responseWithKey(String key, int rows) {
        List<Map<String, Object>> events = new ArrayList<Map<String, Object>>();
        for (int i = 0; i < rows; i++) {
            Map<String, Object> row = new HashMap<String, Object>();
            row.put("index", i);
            events.add(row);
        }
        Map<String, Object> body = new HashMap<String, Object>();
        body.put(key, events);
        return ResponseEntity.ok((Map) body);
    }

    // ---- Analytics ----

    @Test
    public void fetchAnalyticsDataReturnsEventsFromResponse() {
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenReturn(responseWithKey("events", 3));

        List<Map<String, Object>> data = fetcher.fetchAnalyticsData(dateFrom, dateTo, null);

        assertEquals(3, data.size());
        verify(restTemplate, times(1)).getForEntity(anyString(), eq(Map.class));
    }

    @Test
    public void fetchAnalyticsDataCachesSuccessfulResponses() {
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenReturn(responseWithKey("events", 2));

        List<Map<String, Object>> first = fetcher.fetchAnalyticsData(dateFrom, dateTo, null);
        List<Map<String, Object>> second = fetcher.fetchAnalyticsData(dateFrom, dateTo, null);

        assertEquals(first, second);
        // Second call must be served from the cache — only one remote call
        verify(restTemplate, times(1)).getForEntity(anyString(), eq(Map.class));
    }

    @Test
    public void fetchAnalyticsDataUsesDistinctCacheKeyPerMetric() {
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenReturn(responseWithKey("events", 1));

        Map<String, String> params = new HashMap<String, String>();
        params.put("metric", "uploads");

        fetcher.fetchAnalyticsData(dateFrom, dateTo, null);
        fetcher.fetchAnalyticsData(dateFrom, dateTo, params);

        verify(restTemplate, times(2)).getForEntity(anyString(), eq(Map.class));
    }

    @Test
    public void fetchAnalyticsDataPropagatesRemoteFailure() {
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenThrow(new RestClientException("connection refused"));

        try {
            fetcher.fetchAnalyticsData(dateFrom, dateTo, null);
            fail("Expected UncheckedExecutionException");
        } catch (UncheckedExecutionException e) {
            assertTrue(e.getCause() instanceof RestClientException);
        }
    }

    @Test
    public void fetchAnalyticsDataDoesNotCacheFailures() {
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenThrow(new RestClientException("boom"))
                .thenReturn(responseWithKey("events", 4));

        try {
            fetcher.fetchAnalyticsData(dateFrom, dateTo, null);
            fail("Expected UncheckedExecutionException");
        } catch (UncheckedExecutionException expected) {
            // failure must not be cached
        }

        // The next call should retry the remote service and succeed
        List<Map<String, Object>> data = fetcher.fetchAnalyticsData(dateFrom, dateTo, null);
        assertEquals(4, data.size());
        verify(restTemplate, times(2)).getForEntity(anyString(), eq(Map.class));
    }

    @Test
    public void fetchAnalyticsDataReturnsEmptyListWhenBodyHasNoEvents() {
        Map<String, Object> body = new HashMap<String, Object>();
        body.put("other", Collections.emptyList());
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenReturn(ResponseEntity.ok((Map) body));

        List<Map<String, Object>> data = fetcher.fetchAnalyticsData(dateFrom, dateTo, null);

        assertTrue(data.isEmpty());
    }

    // ---- Audit ----

    @Test
    public void fetchAuditDataReturnsEventsFromResponse() {
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenReturn(responseWithKey("events", 5));

        List<Map<String, Object>> data = fetcher.fetchAuditData(dateFrom, dateTo, null);

        assertEquals(5, data.size());
    }

    @Test
    public void fetchAuditDataCachesSuccessfulResponses() {
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenReturn(responseWithKey("events", 2));

        fetcher.fetchAuditData(dateFrom, dateTo, null);
        fetcher.fetchAuditData(dateFrom, dateTo, null);

        verify(restTemplate, times(1)).getForEntity(anyString(), eq(Map.class));
    }

    @Test
    public void fetchAuditDataPropagatesRemoteFailure() {
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenThrow(new RestClientException("unavailable"));

        try {
            fetcher.fetchAuditData(dateFrom, dateTo, null);
            fail("Expected UncheckedExecutionException");
        } catch (UncheckedExecutionException e) {
            assertTrue(e.getCause() instanceof RestClientException);
        }
    }

    // ---- User activity ----

    @Test
    public void fetchUserActivityDataReturnsActivitiesFromResponse() {
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenReturn(responseWithKey("activities", 6));

        List<Map<String, Object>> data = fetcher.fetchUserActivityData(dateFrom, dateTo, null);

        assertEquals(6, data.size());
    }

    @Test
    public void fetchUserActivityDataIsNotCached() {
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenReturn(responseWithKey("activities", 1));

        fetcher.fetchUserActivityData(dateFrom, dateTo, null);
        fetcher.fetchUserActivityData(dateFrom, dateTo, null);

        verify(restTemplate, times(2)).getForEntity(anyString(), eq(Map.class));
    }

    @Test
    public void fetchUserActivityDataFallsBackToSampleDataOnError() {
        when(restTemplate.getForEntity(anyString(), eq(Map.class)))
                .thenThrow(new RestClientException("timeout"));

        List<Map<String, Object>> data = fetcher.fetchUserActivityData(dateFrom, dateTo, null);

        assertEquals(25, data.size());
        assertNotNull(data.get(0).get("user_id"));
        assertNotNull(data.get(0).get("email"));
    }
}
