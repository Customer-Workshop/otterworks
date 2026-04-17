import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-audit',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="audit-page">
      <h1>Audit Log</h1>
      <div class="filters">
        <select class="filter-select">
          <option value="">All Actions</option>
          <option value="create">Create</option>
          <option value="update">Update</option>
          <option value="delete">Delete</option>
          <option value="share">Share</option>
          <option value="login">Login</option>
        </select>
        <input type="date" class="date-filter" />
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>User</th>
            <th>Action</th>
            <th>Resource</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          <!-- TODO: Populate from audit API -->
          <tr>
            <td colspan="5" class="empty-state">No audit events loaded</td>
          </tr>
        </tbody>
      </table>
    </div>
  `,
})
export class AuditComponent implements OnInit {
  ngOnInit(): void {
    // TODO: Fetch audit events from API
  }
}
