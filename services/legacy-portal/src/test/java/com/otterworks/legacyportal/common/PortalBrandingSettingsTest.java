package com.otterworks.legacyportal.common;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.File;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import org.apache.commons.configuration2.ex.ConfigurationException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** Unit tests for the interpolated portal branding settings. */
class PortalBrandingSettingsTest {

    private PortalBrandingSettings settings;

    @TempDir Path tempDir;

    @BeforeEach
    void setUp() throws Exception {
        settings = new PortalBrandingSettings();
        settings.load();
    }

    @AfterEach
    void clearSettingsPath() {
        System.clearProperty(PortalBrandingSettings.SETTINGS_PATH_PROPERTY);
    }

    @Test
    void bannerResolvesOtherSettingsKeys() {
        assertEquals(
                "OtterWorks Portal (on-prem) - contact portal-support@otterworks.example",
                settings.bannerText());
    }

    @Test
    void supportContactIsReadDirectly() {
        assertEquals("portal-support@otterworks.example", settings.supportContact());
    }

    @Test
    void prefixedLookupsInTheSettingsFileAreNotResolved() throws Exception {
        Path settingsFile = tempDir.resolve("portal-settings.properties");
        Path secret = tempDir.resolve("db-password.txt");
        Files.write(secret, "AKIAEXAMPLE_ONPREM_ROTATED".getBytes("UTF-8"));
        Files.write(
                settingsFile,
                ("portal.environment=on-prem\n"
                                + "portal.support=portal-support@otterworks.example\n"
                                + "portal.banner=env=${env:PATH} file=${file:UTF-8:"
                                + secret.toAbsolutePath()
                                + "} user=${sys:user.name} env2=${portal.environment}\n")
                        .getBytes("UTF-8"));
        System.setProperty(
                PortalBrandingSettings.SETTINGS_PATH_PROPERTY,
                settingsFile.toAbsolutePath().toString());

        PortalBrandingSettings operatorSettings = new PortalBrandingSettings();
        operatorSettings.load();

        assertEquals(
                "env=${env:PATH} file=${file:UTF-8:"
                        + secret.toAbsolutePath()
                        + "} user=${sys:user.name} env2=on-prem",
                operatorSettings.bannerText());
    }

    @Test
    void settingsFileInTheWorkingDirectoryIsIgnored() throws Exception {
        File dropped = Paths.get("portal-settings.properties").toAbsolutePath().toFile();
        assertTrue(!dropped.exists(), "working directory must be clean for this test");
        try (PrintWriter writer = new PrintWriter(dropped, "UTF-8")) {
            writer.print("portal.banner=hijacked\nportal.support=attacker@example\n");
        }
        try {
            PortalBrandingSettings reloaded = new PortalBrandingSettings();
            reloaded.load();
            assertEquals(
                    "OtterWorks Portal (on-prem) - contact portal-support@otterworks.example",
                    reloaded.bannerText());
        } finally {
            dropped.delete();
        }
    }

    @Test
    void relativeSettingsPathIsRejected() {
        System.setProperty(
                PortalBrandingSettings.SETTINGS_PATH_PROPERTY, "portal-settings.properties");
        PortalBrandingSettings relative = new PortalBrandingSettings();
        assertThrows(ConfigurationException.class, relative::load);
    }
}
