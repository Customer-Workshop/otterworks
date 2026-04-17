import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="dashboard">
      <h1>Dashboard</h1>
      <div class="stats-grid">
        <div class="stat-card">
          <h3>Total Users</h3>
          <p class="stat-value">{{ totalUsers }}</p>
        </div>
        <div class="stat-card">
          <h3>Active Documents</h3>
          <p class="stat-value">{{ activeDocuments }}</p>
        </div>
        <div class="stat-card">
          <h3>Storage Used</h3>
          <p class="stat-value">{{ storageUsed }}</p>
        </div>
        <div class="stat-card">
          <h3>Active Sessions</h3>
          <p class="stat-value">{{ activeSessions }}</p>
        </div>
      </div>
    </div>
  `,
})
export class DashboardComponent implements OnInit {
  totalUsers = 0;
  activeDocuments = 0;
  storageUsed = '0 GB';
  activeSessions = 0;

  ngOnInit(): void {
    // TODO: Fetch stats from admin API
  }
}
