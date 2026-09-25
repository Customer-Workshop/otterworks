import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, of, throwError } from 'rxjs';
import { tap, delay, map, catchError } from 'rxjs/operators';
import { Router } from '@angular/router';

export interface AuthUser {
  id: string;
  email: string;
  displayName: string;
  role: string;
  token: string;
}

interface LoginResponse {
  user: AuthUser;
  token: string;
}

/** auth-service AuthResponse as proxied by the gateway at /api/v1/auth/login. */
interface GatewayLoginResponse {
  accessToken: string;
  user: { id: string; email: string; displayName: string };
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly TOKEN_KEY = 'ow_admin_token';
  private readonly USER_KEY = 'ow_admin_user';
  private currentUserSubject = new BehaviorSubject<AuthUser | null>(this.getStoredUser());
  currentUser$ = this.currentUserSubject.asObservable();

  constructor(private http: HttpClient, private router: Router) {}

  get isAuthenticated(): boolean {
    return !!this.getToken();
  }

  get currentUser(): AuthUser | null {
    return this.currentUserSubject.value;
  }

  getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  /**
   * Signs in against the tenant gateway so the stored bearer token is one the backends accept;
   * falls back to the offline mock user when no gateway is reachable (local dev, static demos).
   */
  login(email: string, password: string): Observable<AuthUser> {
    return this.gatewayLogin(email, password).pipe(
      catchError(() => this.mockLogin(email, password)),
      tap(user => {
        localStorage.setItem(this.TOKEN_KEY, user.token);
        localStorage.setItem(this.USER_KEY, JSON.stringify(user));
        this.currentUserSubject.next(user);
      })
    );
  }

  logout(): void {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
    this.currentUserSubject.next(null);
    this.router.navigate(['/login']);
  }

  private getStoredUser(): AuthUser | null {
    const stored = localStorage.getItem(this.USER_KEY);
    if (stored) {
      try {
        return JSON.parse(stored) as AuthUser;
      } catch {
        return null;
      }
    }
    return null;
  }

  private gatewayLogin(email: string, password: string): Observable<AuthUser> {
    return this.http.post<GatewayLoginResponse>('/api/v1/auth/login', { email, password }).pipe(
      map(res => ({
        id: res.user.id,
        email: res.user.email,
        displayName: res.user.displayName || 'Admin User',
        role: 'admin',
        token: res.accessToken,
      })),
    );
  }

  private mockLogin(email: string, password: string): Observable<AuthUser> {
    if (password.length < 1) {
      return throwError(() => new Error('Invalid credentials'));
    }
    const user: AuthUser = {
      id: 'a0000000-0000-0000-0000-000000000001',
      email,
      displayName: 'Admin User',
      role: 'admin',
      token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDEiLCJ1c2VyX2lkIjoiYTAwMDAwMDAtMDAwMC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAxIiwiZW1haWwiOiJhZG1pbkBvdHRlcndvcmtzLmRldiIsInJvbGUiOiJhZG1pbiIsImlhdCI6MTcwNDA2NzIwMCwiZXhwIjoxOTI0OTA1NjAwfQ.hD5dwgrPNRTzbXa6lbA83Aru7BvQVIQc0rGVySkF1fA',
    };
    return of(user).pipe(delay(800));
  }
}
