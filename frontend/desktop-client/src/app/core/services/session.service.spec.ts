import { TestBed } from '@angular/core/testing';
import { SessionService } from './session.service';
import { AuthResponse } from '../models/auth.model';

describe('SessionService', () => {
  const authResponse: AuthResponse = {
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    tokenType: 'Bearer',
    expiresIn: 3600,
    user: { id: 'u1', email: 'otter@otterworks.io', displayName: 'Otter Pilot' },
  };

  const create = (): SessionService => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({});
    return TestBed.inject(SessionService);
  };

  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it('starts unauthenticated', () => {
    const service = create();
    expect(service.isAuthenticated()).toBeFalse();
    expect(service.accessToken()).toBeNull();
    expect(service.currentUserName()).toBeNull();
  });

  it('stores the session and exposes the display name', () => {
    const service = create();
    service.setSession(authResponse);

    expect(service.isAuthenticated()).toBeTrue();
    expect(service.accessToken()).toBe('access-token');
    expect(service.refreshToken()).toBe('refresh-token');
    expect(service.user()).toEqual(authResponse.user);
    expect(service.currentUserName()).toBe('Otter Pilot');
  });

  it('falls back to the email when no display name is set', () => {
    const service = create();
    service.setSession({ ...authResponse, user: { id: 'u1', email: 'otter@otterworks.io', displayName: '' } });

    expect(service.currentUserName()).toBe('otter@otterworks.io');
  });

  it('clears the session and the persisted copy', () => {
    const service = create();
    service.setSession(authResponse);
    service.clear();

    expect(service.isAuthenticated()).toBeFalse();
    expect(service.user()).toBeNull();
    expect(localStorage.getItem(SessionService.STORAGE_KEY)).toBeNull();
  });

  it('restores a persisted session on construction', () => {
    create().setSession(authResponse);

    const restored = create();
    expect(restored.isAuthenticated()).toBeTrue();
    expect(restored.accessToken()).toBe('access-token');
    expect(restored.currentUserName()).toBe('Otter Pilot');
  });

  it('ignores a corrupt persisted session', () => {
    localStorage.setItem(SessionService.STORAGE_KEY, 'not json');

    const service = create();
    expect(service.isAuthenticated()).toBeFalse();
  });
});
