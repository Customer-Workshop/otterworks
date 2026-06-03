import jwt from 'jsonwebtoken';
import { createAuthMiddleware, extractUserFromSocket } from '../middleware/auth';
import type { AuthenticatedSocket } from '../middleware/auth';

const JWT_SECRET = 'test-secret-key-for-auth-tests';

const mockLogger = {
  info: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
  debug: jest.fn(),
  fatal: jest.fn(),
  trace: jest.fn(),
  child: jest.fn().mockReturnThis(),
  level: 'info',
} as never;

function createToken(payload: Record<string, unknown>, secret = JWT_SECRET): string {
  return jwt.sign(payload, secret, { expiresIn: '1h' }); // nosemgrep: javascript.jsonwebtoken.security.jwt-hardcode.hardcoded-jwt-secret
}

function createMockSocket(overrides: Partial<{ id: string; auth: any; headers: any }> = {}) {
  return {
    id: overrides.id || 'socket-123',
    handshake: {
      auth: overrides.auth || {},
      headers: overrides.headers || {},
    },
  } as any;
}

describe('createAuthMiddleware', () => {
  const middleware = createAuthMiddleware(JWT_SECRET, mockLogger);

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should reject connection when no token is provided', () => {
    const socket = createMockSocket({ auth: {}, headers: {} });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith(expect.any(Error));
    expect(next.mock.calls[0][0].message).toBe('Authentication required');
  });

  it('should reject connection with an invalid token', () => {
    const socket = createMockSocket({ auth: { token: 'invalid-token' } });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith(expect.any(Error));
    expect(next.mock.calls[0][0].message).toBe('Invalid or expired token');
  });

  it('should reject connection with a token signed with wrong secret', () => {
    const token = createToken({ sub: 'user-1' }, 'wrong-secret');
    const socket = createMockSocket({ auth: { token } });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith(expect.any(Error));
    expect(next.mock.calls[0][0].message).toBe('Invalid or expired token');
  });

  it('should accept a valid token from handshake auth', () => {
    const token = createToken({
      sub: 'user-1',
      email: 'user@test.com',
      name: 'Test User',
      roles: ['user', 'admin'],
    });
    const socket = createMockSocket({ auth: { token } });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    const authSocket = socket as AuthenticatedSocket;
    expect(authSocket.user).toEqual({
      userId: 'user-1',
      email: 'user@test.com',
      displayName: 'Test User',
      roles: ['user', 'admin'],
    });
  });

  it('should accept a valid token from Authorization header', () => {
    const token = createToken({ sub: 'user-2', email: 'user2@test.com', name: 'User Two' });
    const socket = createMockSocket({
      auth: {},
      headers: { authorization: `Bearer ${token}` },
    });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    const authSocket = socket as AuthenticatedSocket;
    expect(authSocket.user?.userId).toBe('user-2');
  });

  it('should use display_name fallback when name is not provided', () => {
    const token = createToken({ sub: 'user-3', display_name: 'Display Name User' });
    const socket = createMockSocket({ auth: { token } });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    const authSocket = socket as AuthenticatedSocket;
    expect(authSocket.user?.displayName).toBe('Display Name User');
  });

  it('should default to Anonymous when no name or display_name', () => {
    const token = createToken({ sub: 'user-4' });
    const socket = createMockSocket({ auth: { token } });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    const authSocket = socket as AuthenticatedSocket;
    expect(authSocket.user?.displayName).toBe('Anonymous');
  });

  it('should default email to empty string when not in token', () => {
    const token = createToken({ sub: 'user-5' });
    const socket = createMockSocket({ auth: { token } });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    const authSocket = socket as AuthenticatedSocket;
    expect(authSocket.user?.email).toBe('');
  });

  it('should default roles to empty array when not in token', () => {
    const token = createToken({ sub: 'user-6' });
    const socket = createMockSocket({ auth: { token } });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    const authSocket = socket as AuthenticatedSocket;
    expect(authSocket.user?.roles).toEqual([]);
  });

  it('should reject an expired token', () => {
    const token = jwt.sign({ sub: 'user-7' }, JWT_SECRET, { expiresIn: '-1h' }); // nosemgrep: javascript.jsonwebtoken.security.jwt-hardcode.hardcoded-jwt-secret
    const socket = createMockSocket({ auth: { token } });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith(expect.any(Error));
    expect(next.mock.calls[0][0].message).toBe('Invalid or expired token');
  });
});

describe('extractUserFromSocket', () => {
  it('should return the authenticated user from the socket', () => {
    const socket = {
      id: 'socket-1',
      user: {
        userId: 'user-1',
        email: 'user@test.com',
        displayName: 'Test User',
        roles: ['user'],
      },
    } as any;

    const user = extractUserFromSocket(socket);

    expect(user).toEqual({
      userId: 'user-1',
      email: 'user@test.com',
      displayName: 'Test User',
      roles: ['user'],
    });
  });

  it('should return anonymous user when socket has no user', () => {
    const socket = { id: 'socket-anon' } as any;

    const user = extractUserFromSocket(socket);

    expect(user.userId).toBe('anon-socket-anon');
    expect(user.email).toBe('');
    expect(user.displayName).toBe('Anonymous');
    expect(user.roles).toEqual([]);
  });
});
