import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { SessionService } from './core/services/session.service';

/**
 * App shell, a port of Views/MainWindow.xaml + ViewModels/MainViewModel.cs: the accent
 * header bar with the "OtterWorks Desktop" wordmark and, once authenticated, the
 * "Signed in as <display name>" area, with the routed view below it.
 */
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet],
  template: `
    <div class="shell">
      <header class="app-bar">
        <div class="wordmark">
          <span class="wordmark-bold">OtterWorks</span>
          <span class="wordmark-light">Desktop</span>
        </div>
        <div class="session" *ngIf="session.isAuthenticated()">
          <span>Signed in as <strong>{{ session.currentUserName() }}</strong></span>
        </div>
      </header>
      <main class="content">
        <router-outlet></router-outlet>
      </main>
    </div>
  `,
  styles: [`
    .shell {
      display: flex;
      flex-direction: column;
      min-height: 100vh;
      background: #f3f4f6;
    }

    .app-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #2f6feb;
      color: #ffffff;
      padding: 12px 18px;
    }

    .wordmark {
      font-size: 20px;
    }

    .wordmark-bold {
      font-weight: bold;
    }

    .wordmark-light {
      color: #dce6ff;
      margin-left: 6px;
    }

    .session {
      margin-right: 12px;
    }

    .content {
      flex: 1;
      min-width: 0;
    }
  `],
})
export class AppComponent {
  readonly session = inject(SessionService);
}
