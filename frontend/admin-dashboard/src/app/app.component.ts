import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  template: `
    <div class="admin-layout">
      <nav class="sidebar">
        <div class="logo">
          <h2>OtterWorks Admin</h2>
        </div>
        <ul class="nav-links">
          <li><a routerLink="/dashboard">Dashboard</a></li>
          <li><a routerLink="/users">Users</a></li>
          <li><a routerLink="/documents">Documents</a></li>
          <li><a routerLink="/system">System Health</a></li>
          <li><a routerLink="/audit">Audit Log</a></li>
          <li><a routerLink="/feature-flags">Feature Flags</a></li>
        </ul>
      </nav>
      <main class="content">
        <router-outlet></router-outlet>
      </main>
    </div>
  `,
})
export class AppComponent {
  title = 'OtterWorks Admin Dashboard';
}
