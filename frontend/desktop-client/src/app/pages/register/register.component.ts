import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-register-page',
  standalone: true,
  imports: [CommonModule],
  template: `
    <section class="placeholder">
      <h2>Create your account</h2>
      <p>This screen is not ported yet.</p>
    </section>
  `,
  styles: [`
    .placeholder {
      padding: 24px;
    }
  `],
})
export class RegisterComponent {}
