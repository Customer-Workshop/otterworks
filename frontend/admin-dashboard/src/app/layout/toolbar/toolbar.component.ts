import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { AuthService } from '../../core/services/auth.service';
import { ThemeService } from '../../services/theme.service';

@Component({
  selector: 'app-toolbar',
  standalone: true,
  imports: [CommonModule, MatToolbarModule, MatIconModule, MatButtonModule, MatMenuModule],
  template: `
    <mat-toolbar class="app-toolbar">
      <span class="toolbar-title">Admin Dashboard</span>
      <span class="spacer"></span>
      <button mat-icon-button (click)="themeService.toggleTheme()" [attr.aria-label]="themeService.darkMode() ? 'Switch to light mode' : 'Switch to dark mode'">
        <mat-icon>{{ themeService.darkMode() ? 'light_mode' : 'dark_mode' }}</mat-icon>
      </button>
      <span class="user-info" *ngIf="authService.currentUser as user">
        <mat-icon>account_circle</mat-icon>
        <span class="user-name">{{ user.displayName }}</span>
      </span>
      <button mat-icon-button [matMenuTriggerFor]="userMenu" aria-label="User menu">
        <mat-icon>more_vert</mat-icon>
      </button>
      <mat-menu #userMenu="matMenu">
        <button mat-menu-item (click)="themeService.toggleTheme()">
          <mat-icon>{{ themeService.darkMode() ? 'light_mode' : 'dark_mode' }}</mat-icon>
          <span>{{ themeService.darkMode() ? 'Light Mode' : 'Dark Mode' }}</span>
        </button>
        <button mat-menu-item (click)="authService.logout()">
          <mat-icon>logout</mat-icon>
          <span>Logout</span>
        </button>
      </mat-menu>
    </mat-toolbar>
  `,
  styles: [`
    .app-toolbar {
      background: var(--bg-surface);
      color: var(--text-primary);
      border-bottom: 1px solid var(--border-color);
      height: 64px;
      box-shadow: 0 1px 3px var(--shadow-color);
    }

    .toolbar-title {
      font-size: 1.1rem;
      font-weight: 500;
    }

    .spacer {
      flex: 1;
    }

    .user-info {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-right: 8px;
      color: var(--text-secondary);
    }

    .user-name {
      font-size: 0.9rem;
    }
  `],
})
export class ToolbarComponent {
  constructor(
    public authService: AuthService,
    public themeService: ThemeService,
  ) {}
}
