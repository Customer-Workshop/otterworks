package com.otterworks.portal.announcements;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AnnouncementRepository extends JpaRepository<Announcement, Long> {

    List<Announcement> findByPublishedTrueOrderByCreatedAtDesc();
}
