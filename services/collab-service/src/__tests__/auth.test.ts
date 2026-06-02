import jwt from 'jsonwebtoken';
import { createAuthMiddleware, extractUserFromSocket } from '../middleware/auth';

const JWT_SECRET = 'test-secret-key-for-unit-tests';

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

function createToken(payload: Record<string, unknown>): string {
  return jwt.sign(payload, JWT_SECRET, { expiresIn: '1h' }); // nosemgrep: javascript.jsonwebtoken.security.jwt-hardcode.hardcoded-jwt-secret
}

function createMockSocket(overrides: Record<string, unknown> = {}): any {
  return {
    id: 'socket-1',
    handshake: {
      auth: {},
      headers: {},
    },
    ...overrides,
  };
}

describe('Auth Middleware', () => {
  describe('createAuthMiddleware', () => {
    const middleware = createAuthMiddleware(JWT_SECRET, mockLogger);

    beforeEach(() => {
      jest.clearAllMocks();
    });

    it('should reject connection with no token', () => {
      const socket = createMockSocket();
      const next = jest.fn();

      middleware(socket, next);

      expect(next).toHaveBeenCalledWith(expect.any(Error));
      expect(next.mock.calls[0][0].message).toBe('Authentication required');
    });

    it('should accept valid token from handshake auth', () => {
      const token = createToken({ sub: 'user-1', email: 'test@example.com', name: 'Test User' });
      const socket = createMockSocket({
        handshake: { auth: { token }, headers: {} },
      });
      const next = jest.fn();

      middleware(socket, next);

      expect(next).toHaveBeenCalledWith();
      expect(socket.user).toBeDefined();
      expect(socket.user.userId).toBe('user-1');
      expect(socket.user.email).toBe('test@example.com');
      expect(socket.user.displayName).toBe('Test User');
    });

    it('should accept valid token from Authorization header', () => {
      const token = createToken({ sub: 'user-2', email: 'user2@example.com' });
      const socket = createMockSocket({
        handshake: {
          auth: {},
          headers: { authorization: `Bearer ${token}` },
        },
      });
      const next = jest.fn();

      middleware(socket, next);

      expect(next).toHaveBeenCalledWith();
      expect(socket.user.userId).toBe('user-2');
    });

    it('should reject expired token', () => {
      const token = jwt.sign({ sub: 'user-1' }, JWT_SECRET, { expiresIn: '-1h' }); // nosemgrep: javascript.jsonwebtoken.security.jwt-hardcode.hardcoded-jwt-secret
      const socket = createMockSocket({
        handshake: { auth: { token }, headers: {} },
      });
      const next = jest.fn();

      middleware(socket, next);

      expect(next).toHaveBeenCalledWith(expect.any(Error));
      expect(next.mock.calls[0][0].message).toBe('Invalid or expired token');
    });

    it('should reject token signed with wrong secret', () => {
      const token = jwt.sign({ sub: 'user-1' }, 'wrong-secret', { expiresIn: '1h' }); // nosemgrep: javascript.jsonwebtoken.security.jwt-hardcode.hardcoded-jwt-secret
      const socket = createMockSocket({
        handshake: { auth: { token }, headers: {} },
      });
      const next = jest.fn();

      middleware(socket, next);

      expect(next).toHaveBeenCalledWith(expect.any(Error));
      expect(next.mock.calls[0][0].message).toBe('Invalid or expired token');
    });

    it('should use display_name fallback when name is missing', () => {
      const token = createToken({ sub: 'user-3', display_name: 'Display Name' });
      const socket = createMockSocket({
        handshake: { auth: { token }, headers: {} },
      });
      const next = jest.fn();

      middleware(socket, next);

      expect(next).toHaveBeenCalledWith();
      expect(socket.user.displayName).toBe('Display Name');
    });

    it('should default displayName to Anonymous when no name fields present', () => {
      const token = createToken({ sub: 'user-4' });
      const socket = createMockSocket({
        handshake: { auth: { token }, headers: {} },
      });
      const next = jest.fn();

      middleware(socket, next);

      expect(next).toHaveBeenCalledWith();
      expect(socket.user.displayName).toBe('Anonymous');
    });

    it('should parse roles from token', () => {
      const token = createToken({ sub: 'user-5', roles: ['admin', 'editor'] });
      const socket = createMockSocket({
        handshake: { auth: { token }, headers: {} },
      });
      const next = jest.fn();

      middleware(socket, next);

      expect(socket.user.roles).toEqual(['admin', 'editor']);
    });

    it('should default roles to empty array', () => {
      const token = createToken({ sub: 'user-6' });
      const socket = createMockSocket({
        handshake: { auth: { token }, headers: {} },
      });
      const next = jest.fn();

      middleware(socket, next);

      expect(socket.user.roles).toEqual([]);
    });
  });

  describe('extractUserFromSocket', () => {
    it('should return user from authenticated socket', () => {
      const socket = {
        id: 'socket-1',
        user: {
          userId: 'user-1',
          email: 'test@example.com',
          displayName: 'Test',
          roles: ['viewer'],
        },
      } as any;

      const user = extractUserFromSocket(socket);
      expect(user.userId).toBe('user-1');
      expect(user.email).toBe('test@example.com');
    });

    it('should return anonymous user for unauthenticated socket', () => {
      const socket = { id: 'socket-99' } as any;

      const user = extractUserFromSocket(socket);
      expect(user.userId).toBe('anon-socket-99');
      expect(user.email).toBe('');
      expect(user.displayName).toBe('Anonymous');
      expect(user.roles).toEqual([]);
    });
  });
});
