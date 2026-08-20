package com.otterworks.legacyportal.common;

import java.io.File;
import java.net.URL;
import javax.annotation.PostConstruct;
import org.apache.commons.configuration2.Configuration;
import org.apache.commons.configuration2.ConfigurationLookup;
import org.apache.commons.configuration2.PropertiesConfiguration;
import org.apache.commons.configuration2.builder.FileBasedConfigurationBuilder;
import org.apache.commons.configuration2.builder.fluent.Parameters;
import org.apache.commons.configuration2.builder.fluent.PropertiesBuilderParameters;
import org.apache.commons.configuration2.ex.ConfigurationException;
import org.apache.commons.configuration2.interpol.ConfigurationInterpolator;
import org.springframework.stereotype.Component;

/**
 * Portal branding strings, loaded from {@code portal-settings.properties} with Commons
 * Configuration so operations can edit them on the VM without a redeploy.
 *
 * <p>The settings file uses {@code ${...}} interpolation, but only key-to-key references
 * ({@code ${portal.environment}}) resolve: the interpolator backing the settings this
 * component reads has no prefixed lookups registered, so {@code ${env:...}},
 * {@code ${file:...}} and friends are returned verbatim. The values are served
 * unauthenticated on {@code /health}, so the settings file must never be able to read the
 * process environment or the filesystem.
 *
 * <p>The file is read from the packaged classpath resource. An operator may point the
 * service at an alternative file with the {@value #SETTINGS_PATH_PROPERTY} system property,
 * which must be an absolute path; the process working directory is never searched.
 */
@Component
public class PortalBrandingSettings {

    private static final String SETTINGS_FILE = "portal-settings.properties";

    /** System property holding an absolute path to an operator-managed settings file. */
    public static final String SETTINGS_PATH_PROPERTY = "portal.settings.path";

    private Configuration configuration;
    private Configuration templateConfiguration;

    @PostConstruct
    public void load() throws ConfigurationException {
        Configuration settings = readSettings();
        restrictInterpolator(settings);
        this.configuration = settings;
        this.templateConfiguration = readSettings();
    }

    public String bannerText() {
        return configuration.getString("portal.banner", "OtterWorks Portal");
    }

    public String supportContact() {
        return configuration.getString("portal.support", "");
    }

    /**
     * Resolve an arbitrary settings template through the configuration's interpolator.
     * Used by the dependency transcript that pins the interpolation behavior of the
     * Commons Text release on the classpath. Unlike the settings this component serves,
     * templates passed here are supplied by trusted callers, not by the settings file.
     */
    public String interpolate(String template) {
        return String.valueOf(templateConfiguration.getInterpolator().interpolate(template));
    }

    private Configuration readSettings() throws ConfigurationException {
        PropertiesBuilderParameters parameters =
                new Parameters().properties().setThrowExceptionOnMissing(false);
        String configuredPath = System.getProperty(SETTINGS_PATH_PROPERTY);
        if (configuredPath != null && !configuredPath.trim().isEmpty()) {
            File settingsFile = new File(configuredPath.trim());
            if (!settingsFile.isAbsolute()) {
                throw new ConfigurationException(
                        SETTINGS_PATH_PROPERTY + " must be an absolute path: " + configuredPath);
            }
            parameters = parameters.setFile(settingsFile);
        } else {
            URL packaged = PortalBrandingSettings.class.getClassLoader().getResource(SETTINGS_FILE);
            if (packaged == null) {
                throw new ConfigurationException("packaged " + SETTINGS_FILE + " is missing");
            }
            parameters = parameters.setURL(packaged);
        }
        return new FileBasedConfigurationBuilder<>(PropertiesConfiguration.class)
                .configure(parameters)
                .getConfiguration();
    }

    /** Leave key-to-key interpolation in place and drop every prefixed lookup. */
    private void restrictInterpolator(Configuration settings) {
        ConfigurationInterpolator keysOnly = new ConfigurationInterpolator();
        keysOnly.addDefaultLookup(new ConfigurationLookup(settings));
        settings.setInterpolator(keysOnly);
    }
}
