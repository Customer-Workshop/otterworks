package com.otterworks.billing.repository;

import com.otterworks.billing.model.Plan;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PlanRepository extends JpaRepository<Plan, String> {}
