import { Injectable, signal, effect, OnDestroy } from '@angular/core';

const THEME_STORAGE_KEY = 'ow_admin_theme';

@Injectable({ providedIn: 'root' })
export class ThemeService implements OnDestroy {
  readonly darkMode = signal(false);

  private mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  private mediaListener = (e: MediaQueryListEvent) => this.onSystemChange(e);
  private hasExplicitPreference = false;

  constructor() {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored !== null) {
      this.hasExplicitPreference = true;
      this.darkMode.set(stored === 'dark');
    } else {
      this.darkMode.set(this.mediaQuery.matches);
    }

    this.mediaQuery.addEventListener('change', this.mediaListener);

    effect(() => {
      const isDark = this.darkMode();
      if (isDark) {
        document.body.classList.add('dark-theme');
      } else {
        document.body.classList.remove('dark-theme');
      }
    });
  }

  ngOnDestroy(): void {
    this.mediaQuery.removeEventListener('change', this.mediaListener);
  }

  toggleTheme(): void {
    this.hasExplicitPreference = true;
    const newValue = !this.darkMode();
    this.darkMode.set(newValue);
    localStorage.setItem(THEME_STORAGE_KEY, newValue ? 'dark' : 'light');
  }

  private onSystemChange(e: MediaQueryListEvent): void {
    if (!this.hasExplicitPreference) {
      this.darkMode.set(e.matches);
    }
  }
}
