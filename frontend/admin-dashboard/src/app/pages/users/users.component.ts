import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-users',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="users-page">
      <h1>User Management</h1>
      <div class="toolbar">
        <input type="text" placeholder="Search users..." class="search-input" />
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Display Name</th>
            <th>Role</th>
            <th>Status</th>
            <th>Last Login</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <!-- TODO: Populate from admin API -->
          <tr>
            <td colspan="6" class="empty-state">No users loaded</td>
          </tr>
        </tbody>
      </table>
    </div>
  `,
})
export class UsersComponent implements OnInit {
  ngOnInit(): void {
    // TODO: Fetch users from admin API
  }
}
