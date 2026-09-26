import { Injectable, computed, signal } from '@angular/core';
import { AuthResponse, AuthUser } from '../models/auth.model';

interface PersistedSession {
  accessToken: string;
  refreshToken: string | null;
  user: AuthUser | null;
}

/**
 * Browser equivalent of Services/SessionState.cs: holds the JWT access token, the refresh
 * token and the current user. Where the WPF client persisted the session DPAPI-encrypted
 * under %APPDATA%, the browser persists it in localStorage and restores it on construction.
 */
@Injectable({ providedIn: 'root' })
export class SessionService {
  static readonly STORAGE_KEY = 'ow_desktop_session';

  private readonly accessTokenSignal = signal<string | null>(null);
  private readonly refreshTokenSignal = signal<string | null>(null);
  private readonly userSignal = signal<AuthUser | null>(null);

  readonly accessToken = this.accessTokenSignal.asReadonly();
  readonly refreshToken = this.refreshTokenSignal.asReadonly();
  readonly user = this.userSignal.asReadonly();

  /** True while an access token is held (port of SessionState.IsAuthenticated). */
  readonly isAuthenticated = computed(() => !!this.accessTokenSignal());

  /** The current user's display name, falling back to their email (port of MainViewModel.CurrentUserName). */
  readonly currentUserName = computed(() => {
    const user = this.userSignal();
    if (!user) {
      return null;
    }
    return user.displayName || user.email || null;
  });

  constructor() {
    this.restore();
  }

  setSession(response: AuthResponse): void {
    this.accessTokenSignal.set(response.accessToken ?? null);
    this.refreshTokenSignal.set(response.refreshToken ?? null);
    this.userSignal.set(response.user ?? null);
    this.save();
  }

  clear(): void {
    this.accessTokenSignal.set(null);
    this.refreshTokenSignal.set(null);
    this.userSignal.set(null);
    try {
      localStorage.removeItem(SessionService.STORAGE_KEY);
    } catch {
      // Storage is best-effort; the in-memory session still works.
    }
  }

  /** Restores a persisted session. Returns true if one was loaded (port of TryRestore). */
  restore(): boolean {
    let raw: string | null = null;
    try {
      raw = localStorage.getItem(SessionService.STORAGE_KEY);
    } catch {
      return false;
    }

    if (!raw) {
      return false;
    }

    try {
      const session = JSON.parse(raw) as PersistedSession | null;
      if (session && session.accessToken) {
        this.accessTokenSignal.set(session.accessToken);
        this.refreshTokenSignal.set(session.refreshToken ?? null);
        this.userSignal.set(session.user ?? null);
        return true;
      }
    } catch {
      this.clear();
    }

    return false;
  }

  private save(): void {
    const session: PersistedSession = {
      accessToken: this.accessTokenSignal() ?? '',
      refreshToken: this.refreshTokenSignal(),
      user: this.userSignal(),
    };
    try {
      localStorage.setItem(SessionService.STORAGE_KEY, JSON.stringify(session));
    } catch {
      // Persistence is best-effort; the in-memory session still works.
    }
  }
}
