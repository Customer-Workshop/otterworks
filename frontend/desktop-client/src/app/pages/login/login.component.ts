import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { ApiError } from '../../core/models/api-error';
import { OtterWorksApiService } from '../../core/services/otterworks-api.service';
import { SessionService } from '../../core/services/session.service';

/**
 * Port of Views/LoginView.xaml + ViewModels/LoginViewModel.cs: a centered sign-in card
 * with email and password, a single server-error message block, an indeterminate busy
 * bar and a link to Register.
 */
@Component({
  selector: 'app-login-page',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
  ],
  template: `
    <div class="login-page">
      <div class="login-card">
        <h1 class="title">Sign in</h1>
        <p class="subtitle">Welcome back to OtterWorks.</p>

        <form class="login-form" [formGroup]="loginForm" (ngSubmit)="onSubmit()">
          <label class="field-label" for="login-email">Email</label>
          <mat-form-field appearance="outline" class="full-width">
            <input matInput id="login-email" type="email" formControlName="email" autocomplete="username" />
          </mat-form-field>

          <label class="field-label" for="login-password">Password</label>
          <mat-form-field appearance="outline" class="full-width">
            <input
              matInput
              id="login-password"
              type="password"
              formControlName="password"
              autocomplete="current-password"
            />
          </mat-form-field>

          <p class="error-message" *ngIf="errorMessage">{{ errorMessage }}</p>

          <button
            mat-flat-button
            color="primary"
            type="submit"
            class="submit-button"
            [disabled]="!canSubmit()"
          >
            Sign in
          </button>

          <mat-progress-bar class="busy-bar" mode="indeterminate" *ngIf="isBusy"></mat-progress-bar>
        </form>

        <div class="footer">
          <span class="footer-text">No account?</span>
          <button type="button" class="link-button" (click)="goToRegister()">Create one</button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .login-page {
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: calc(100vh - 56px);
      background: #f3f4f6;
      padding: 24px;
    }

    .login-card {
      box-sizing: border-box;
      width: 380px;
      padding: 32px;
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      box-shadow: 0 2px 18px rgba(0, 0, 0, 0.12);
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

    .login-form {
      display: flex;
      flex-direction: column;
    }

    .field-label {
      font-weight: 600;
      margin-bottom: 4px;
      color: #111827;
    }

    .full-width {
      width: 100%;
    }

    .error-message {
      margin: 4px 0 0;
      color: #d64545;
      overflow-wrap: anywhere;
    }

    .submit-button {
      width: 100%;
      margin-top: 20px;
      border-radius: 6px;
      font-weight: 600;
    }

    .busy-bar {
      margin-top: 10px;
      height: 3px;
    }

    .footer {
      display: flex;
      align-items: center;
      justify-content: center;
      margin-top: 18px;
    }

    .footer-text {
      color: #6b7280;
    }

    .link-button {
      margin-left: 6px;
      padding: 0;
      border: 0;
      background: transparent;
      color: #2f6feb;
      font: inherit;
      cursor: pointer;
    }
  `],
})
export class LoginComponent {
  private readonly formBuilder = inject(FormBuilder);
  private readonly api = inject(OtterWorksApiService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  readonly loginForm = this.formBuilder.nonNullable.group({
    email: '',
    password: '',
  });

  errorMessage: string | null = null;
  isBusy = false;

  /**
   * Port of LoginViewModel.CanSubmit: no client-side format or length checks, just a
   * non-blank email and a non-empty password while no request is in flight.
   */
  canSubmit(): boolean {
    const { email, password } = this.loginForm.getRawValue();
    return !this.isBusy && email.trim().length > 0 && password.length > 0;
  }

  onSubmit(): void {
    if (!this.canSubmit()) {
      return;
    }

    const { email, password } = this.loginForm.getRawValue();
    this.errorMessage = null;
    this.isBusy = true;

    this.api.login(email.trim(), password).subscribe({
      next: response => {
        this.isBusy = false;
        if (!response?.accessToken) {
          this.errorMessage = 'Login succeeded but the server returned an empty response.';
          return;
        }

        this.session.setSession(response);
        void this.router.navigate(['/documents']);
      },
      error: (error: unknown) => {
        this.isBusy = false;
        this.errorMessage =
          error instanceof ApiError || error instanceof Error
            ? error.message
            : String(error);
      },
    });
  }

  goToRegister(): void {
    void this.router.navigate(['/register']);
  }
}
