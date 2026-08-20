package com.otterworks.portal.announcements;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** Contract §2.1 branch selection, §2.2/§2.4 not-found message, §2.4 idempotent publish. */
class AnnouncementServiceTest {

    private final AnnouncementRepository repository = mock(AnnouncementRepository.class);
    private final AnnouncementService service = new AnnouncementService(repository);

    @Test
    void listPublishedUsesTheOrderedFinder() {
        Announcement a = new Announcement("t", "b", true);
        when(repository.findByPublishedTrueOrderByCreatedAtDesc()).thenReturn(List.of(a));

        assertThat(service.listPublished()).containsExactly(a);
        verify(repository, never()).findAll();
    }

    /** §2.1: the publishedOnly=false branch is findAll(), with no ORDER BY. */
    @Test
    void listAllUsesFindAllWithoutOrdering() {
        Announcement a = new Announcement("t", "b", false);
        when(repository.findAll()).thenReturn(List.of(a));

        assertThat(service.listAll()).containsExactly(a);
        verify(repository, never()).findByPublishedTrueOrderByCreatedAtDesc();
    }

    @Test
    void createHonoursPublishedTrue() {
        when(repository.save(any(Announcement.class))).thenAnswer(i -> i.getArgument(0));

        Announcement created = service.create("t", "b", true);

        assertThat(created.isPublished()).isTrue();
        assertThat(created.getCreatedAt()).isNotNull();
    }

    @Test
    void unknownIdThrowsWithTheContractMessage() {
        when(repository.findById(999999L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.get(999999L))
                .isInstanceOf(NoSuchElementException.class)
                .hasMessage("announcement 999999 not found");
    }

    @Test
    void publishAnAlreadyPublishedAnnouncementIsIdempotent() {
        Announcement published = new Announcement("t", "b", true);
        when(repository.findById(1L)).thenReturn(Optional.of(published));
        when(repository.save(any(Announcement.class))).thenAnswer(i -> i.getArgument(0));

        Announcement result = service.publish(1L);

        assertThat(result.isPublished()).isTrue();
        assertThat(result.getCreatedAt()).isEqualTo(published.getCreatedAt());
    }

    @Test
    void publishUnknownIdThrowsWithTheContractMessage() {
        when(repository.findById(42L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.publish(42L))
                .isInstanceOf(NoSuchElementException.class)
                .hasMessage("announcement 42 not found");
    }
}
