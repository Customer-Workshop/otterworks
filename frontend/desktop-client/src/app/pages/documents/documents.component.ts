import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-documents-page',
  standalone: true,
  imports: [CommonModule],
  template: `
    <section class="placeholder">
      <h2>Documents</h2>
      <p>This screen is not ported yet.</p>
    </section>
  `,
  styles: [`
    .placeholder {
      padding: 24px;
    }
  `],
})
export class DocumentsComponent {}
