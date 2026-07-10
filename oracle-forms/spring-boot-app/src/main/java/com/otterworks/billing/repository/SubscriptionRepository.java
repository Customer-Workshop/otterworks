package com.otterworks.billing.repository;

import com.otterworks.billing.model.Subscription;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SubscriptionRepository extends JpaRepository<Subscription, Long> {
  List<Subscription> findByCustomerId(Long customerId);
}
