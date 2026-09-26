import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { toSignal } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { AuthResponse } from '../../core/models/auth.model';
import { OtterWorksApiService } from '../../core/services/otterworks-api.service';
import { SessionService } from '../../core/services/session.service';

/**
 * Port of Views/RegisterView.xaml + ViewModels/RegisterViewModel.cs: the centered
 * "Create account" card with display name, email and password, a single shared error
 * line, an indeterminate progress bar while the POST is in flight, and a footer link
 * back to the login screen.
 */
@Component({
  selector: 'app-register-page',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
  ],
  template: `
    <div class="page">
      <mat-card class="card">
        <h1 class="title">Create account</h1>
        <p class="subtitle">Get started with OtterWorks.</p>

        <form [formGroup]="form" (ngSubmit)="register()">
          <label class="field-label" for="displayName">Display name</label>
          <mat-form-field appearance="outline" class="full-width">
            <input matInput id="displayName" type="text" formControlName="displayName" />
          </mat-form-field>

          <label class="field-label" for="email">Email</label>
          <mat-form-field appearance="outline" class="full-width">
            <input matInput id="email" type="text" formControlName="email" />
          </mat-form-field>

          <label class="field-label" for="password">Password</label>
          <mat-form-field appearance="outline" class="full-width">
            <input matInput id="password" type="password" formControlName="password" />
          </mat-form-field>
          <p class="hint">At least 8 characters.</p>

          <p class="error" *ngIf="errorMessage()">{{ errorMessage() }}</p>

          <button
            mat-flat-button
            color="primary"
            type="submit"
            class="submit"
            [disabled]="!canSubmit()"
          >
            Create account
          </button>

          <mat-progress-bar
            class="progress"
            mode="indeterminate"
            *ngIf="isBusy()"
          ></mat-progress-bar>
        </form>

        <div class="footer">
          <span class="muted">Already have an account?</span>
          <a class="link" routerLink="/login">Sign in</a>
        </div>
      </mat-card>
    </div>
  `,
  styles: [`
    .page {
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: calc(100vh - 56px);
      padding: 24px;
      background: #f3f4f6;
    }

    .card {
      width: 380px;
      padding: 32px;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      box-shadow: 0 2px 18px rgba(0, 0, 0, 0.12);
      background: #ffffff;
    }

    .title {
      margin: 0;
      font-size: 24px;
      font-weight: bold;
      color: #111827;
    }

    .subtitle {
      margin: 4px 0 20px;
      color: #6b7280;
    }

    .field-label {
      display: block;
      font-weight: 600;
      margin-bottom: 4px;
      color: #111827;
    }

    .full-width {
      width: 100%;
    }

    .hint {
      margin: 0;
      font-size: 11px;
      color: #6b7280;
    }

    .error {
      margin: 14px 0 0;
      color: #d64545;
      overflow-wrap: anywhere;
    }

    .submit {
      display: block;
      width: 100%;
      margin-top: 20px;
      height: 40px;
      border-radius: 6px;
      font-weight: 600;
    }

    .progress {
      margin-top: 10px;
      height: 3px;
    }

    .footer {
      display: flex;
      align-items: center;
      justify-content: center;
      margin-top: 18px;
    }

    .muted {
      color: #6b7280;
    }

    .link {
      margin-left: 6px;
      color: #2f6feb;
      cursor: pointer;
      text-decoration: none;
      background: transparent;
    }
  `],
})
export class RegisterComponent {
  private readonly api = inject(OtterWorksApiService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  readonly form = new FormGroup({
    displayName: new FormControl('', { nonNullable: true }),
    email: new FormControl('', { nonNullable: true }),
    password: new FormControl('', { nonNullable: true }),
  });

  readonly isBusy = signal(false);
  readonly errorMessage = signal<string | null>(null);

  /** Re-evaluated on every keystroke, like UpdateSourceTrigger=PropertyChanged in WPF. */
  private readonly value = toSignal(this.form.valueChanges, {
    initialValue: this.form.getRawValue(),
  });

  /**
   * Port of RegisterViewModel.CanSubmit: display name and email must be non-blank, the
   * password merely non-empty (whitespace counts), and no request may be in flight.
   */
  readonly canSubmit = computed(() => {
    const value = this.value();
    return (
      !this.isBusy() &&
      (value.displayName ?? '').trim().length > 0 &&
      (value.email ?? '').trim().length > 0 &&
      (value.password ?? '').length > 0
    );
  });

  register(): void {
    if (!this.canSubmit()) {
      return;
    }

    this.errorMessage.set(null);

    const { displayName, email, password } = this.form.getRawValue();
    if (password.length < 8) {
      this.errorMessage.set('Password must be at least 8 characters.');
      return;
    }

    this.isBusy.set(true);
    this.api.register(displayName.trim(), email.trim(), password).subscribe({
      next: (response: AuthResponse | null) => {
        this.isBusy.set(false);
        if (!response?.accessToken) {
          this.errorMessage.set(
            'Registration succeeded but the server returned an empty response.'
          );
          return;
        }

        this.session.setSession(response);
        void this.router.navigate(['/documents']);
      },
      error: (error: Error) => {
        this.isBusy.set(false);
        this.errorMessage.set(error.message || 'Registration failed.');
      },
    });
  }
}
