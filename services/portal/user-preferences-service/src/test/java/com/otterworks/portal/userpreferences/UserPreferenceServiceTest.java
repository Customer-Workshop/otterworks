package com.otterworks.portal.userpreferences;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** Contract §2.1 (fabricated, unpersisted defaults) and §2.2 (upsert is a full replace). */
@ExtendWith(MockitoExtension.class)
class UserPreferenceServiceTest {

    @Mock private UserPreferenceRepository repository;

    @Test
    void unknownUserGetsFabricatedDefaultsThatAreNotPersisted() {
        when(repository.findById("nobody")).thenReturn(Optional.empty());

        UserPreferenceService service = new UserPreferenceService(repository);
        UserPreference first = service.getOrDefault("nobody");
        UserPreference second = service.getOrDefault("nobody");

        assertThat(first.getUserId()).isEqualTo("nobody");
        assertThat(first.getTheme()).isEqualTo("light");
        assertThat(first.getLocale()).isEqualTo("en-US");
        assertThat(first.isEmailNotifications()).isTrue();
        assertThat(second.getTheme()).isEqualTo("light");
        verify(repository, never()).save(any());
    }

    @Test
    void saveForAnAbsentUserWritesAllThreeFields() {
        when(repository.findById("u1")).thenReturn(Optional.empty());
        when(repository.save(any(UserPreference.class))).thenAnswer(i -> i.getArgument(0));

        UserPreference saved =
                new UserPreferenceService(repository).save("u1", "dark", "fr-FR", false);

        ArgumentCaptor<UserPreference> captor = ArgumentCaptor.forClass(UserPreference.class);
        verify(repository).save(captor.capture());
        assertThat(captor.getValue().getUserId()).isEqualTo("u1");
        assertThat(saved.getTheme()).isEqualTo("dark");
        assertThat(saved.getLocale()).isEqualTo("fr-FR");
        assertThat(saved.isEmailNotifications()).isFalse();
    }

    @Test
    void saveForAStoredUserOverwritesEveryField() {
        UserPreference stored = new UserPreference("u1", "dark", "fr-FR", false);
        when(repository.findById("u1")).thenReturn(Optional.of(stored));
        when(repository.save(any(UserPreference.class))).thenAnswer(i -> i.getArgument(0));

        UserPreference saved =
                new UserPreferenceService(repository).save("u1", "solarized", "zz-ZZ", true);

        assertThat(saved).isSameAs(stored);
        assertThat(saved.getTheme()).isEqualTo("solarized");
        assertThat(saved.getLocale()).isEqualTo("zz-ZZ");
        assertThat(saved.isEmailNotifications()).isTrue();
    }

    @Test
    void userIdIsOpaqueAndEchoedVerbatim() {
        when(repository.findById(anyString())).thenReturn(Optional.empty());

        String odd = "  ünïcøde/../%20 ";
        assertThat(new UserPreferenceService(repository).getOrDefault(odd).getUserId())
                .isEqualTo(odd);
    }
}
