package com.otterworks.legacyportal.common;

import jakarta.annotation.PostConstruct;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import org.apache.commons.configuration2.Configuration;
import org.apache.commons.configuration2.PropertiesConfiguration;
import org.apache.commons.configuration2.ex.ConfigurationException;
import org.apache.commons.configuration2.io.FileHandler;
import org.springframework.stereotype.Component;

/**
 * Portal branding strings, loaded from {@code portal-settings.properties} with Commons
 * Configuration so operations can edit them on the VM without a redeploy.
 *
 * <p>The settings file uses {@code ${...}} interpolation (other keys plus the default
 * prefixed lookups), which is why this loads through Commons Configuration rather than
 * Spring's own property binding.
 */
@Component
public class PortalBrandingSettings {

    private static final String SETTINGS_FILE = "portal-settings.properties";

    private Configuration configuration;

    @PostConstruct
    public void load() throws ConfigurationException {
        PropertiesConfiguration properties = new PropertiesConfiguration();
        FileHandler handler = new FileHandler(properties);
        File settingsFile = new File(SETTINGS_FILE);
        if (settingsFile.isFile()) {
            handler.load(settingsFile);
        } else {
            try (InputStream resource =
                    PortalBrandingSettings.class.getClassLoader().getResourceAsStream(SETTINGS_FILE)) {
                if (resource != null) {
                    handler.load(resource);
                }
            } catch (IOException exception) {
                throw new ConfigurationException("Unable to close portal settings resource", exception);
            }
        }
        this.configuration = properties;
    }

    public String bannerText() {
        return configuration.getString("portal.banner", "OtterWorks Portal");
    }

    public String supportContact() {
        return configuration.getString("portal.support", "");
    }

    /**
     * Resolve an arbitrary settings template through the configuration's interpolator.
     * Used by the settings file itself and by the dependency transcript that pins the
     * interpolation behavior of the Commons Text release on the classpath.
     */
    public String interpolate(String template) {
        return String.valueOf(configuration.getInterpolator().interpolate(template));
    }
}
