import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-login-page',
  standalone: true,
  imports: [CommonModule],
  template: `
    <section class="placeholder">
      <h2>Sign in</h2>
      <p>This screen is not ported yet.</p>
    </section>
  `,
  styles: [`
    .placeholder {
      padding: 24px;
    }
  `],
})
export class LoginComponent {}
