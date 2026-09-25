package com.otterworks.report.config;

import com.otterworks.report.archive.ArchiveProperties;
import com.otterworks.report.archive.ArchiveStoreRegistry;
import com.otterworks.report.reconciliation.ReconciliationRepository;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Wires the archive read path. Nothing here touches the report database; when
 * {@code ARCHIVE_STORE} is unset the registry is inert and the golden app is unchanged.
 */
@Configuration
@EnableConfigurationProperties(ArchiveProperties.class)
public class ArchiveConfig {

    @Bean
    public ArchiveStoreRegistry archiveStoreRegistry(ArchiveProperties properties) {
        return new ArchiveStoreRegistry(properties);
    }

    @Bean
    public ReconciliationRepository reconciliationRepository(ArchiveStoreRegistry registry) {
        return new ReconciliationRepository(registry);
    }
}
