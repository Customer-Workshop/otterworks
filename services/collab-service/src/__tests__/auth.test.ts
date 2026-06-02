import jwt from 'jsonwebtoken';
import {
  createAuthMiddleware,
  extractUserFromSocket,
  type AuthenticatedSocket,
} from '../middleware/auth';

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

function createMockSocket(overrides: Record<string, unknown> = {}): any {
  return {
    id: 'socket-123',
    handshake: {
      auth: {},
      headers: {},
    },
    ...overrides,
  };
}

describe('createAuthMiddleware', () => {
  const middleware = createAuthMiddleware(JWT_SECRET, mockLogger);

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should reject connection when no token is provided', () => {
    const socket = createMockSocket();
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith(expect.any(Error));
    expect(next.mock.calls[0][0].message).toBe('Authentication required');
  });

  it('should authenticate with valid token from auth object', () => {
    const token = jwt.sign(
      { sub: 'user-1', email: 'alice@test.com', name: 'Alice', roles: ['USER'] },
      JWT_SECRET,
    );
    const socket = createMockSocket({
      handshake: {
        auth: { token },
        headers: {},
      },
    });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    expect((socket as AuthenticatedSocket).user).toBeDefined();
    expect((socket as AuthenticatedSocket).user!.userId).toBe('user-1');
    expect((socket as AuthenticatedSocket).user!.email).toBe('alice@test.com');
    expect((socket as AuthenticatedSocket).user!.displayName).toBe('Alice');
    expect((socket as AuthenticatedSocket).user!.roles).toEqual(['USER']);
  });

  it('should authenticate with token from authorization header', () => {
    const token = jwt.sign({ sub: 'user-2', email: 'bob@test.com' }, JWT_SECRET);
    const socket = createMockSocket({
      handshake: {
        auth: {},
        headers: { authorization: `Bearer ${token}` },
      },
    });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    expect((socket as AuthenticatedSocket).user!.userId).toBe('user-2');
  });

  it('should reject with invalid token', () => {
    const socket = createMockSocket({
      handshake: {
        auth: { token: 'invalid.token.here' },
        headers: {},
      },
    });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith(expect.any(Error));
    expect(next.mock.calls[0][0].message).toBe('Invalid or expired token');
  });

  it('should reject with expired token', () => {
    const token = jwt.sign({ sub: 'user-1', email: 'test@test.com' }, JWT_SECRET, {
      expiresIn: '-1h',
    });
    const socket = createMockSocket({
      handshake: {
        auth: { token },
        headers: {},
      },
    });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith(expect.any(Error));
    expect(next.mock.calls[0][0].message).toBe('Invalid or expired token');
  });

  it('should use display_name when name is absent', () => {
    const token = jwt.sign({ sub: 'user-3', display_name: 'Charlie Brown' }, JWT_SECRET);
    const socket = createMockSocket({
      handshake: {
        auth: { token },
        headers: {},
      },
    });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    expect((socket as AuthenticatedSocket).user!.displayName).toBe('Charlie Brown');
  });

  it('should default displayName to Anonymous when neither name nor display_name', () => {
    const token = jwt.sign({ sub: 'user-4' }, JWT_SECRET);
    const socket = createMockSocket({
      handshake: {
        auth: { token },
        headers: {},
      },
    });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    expect((socket as AuthenticatedSocket).user!.displayName).toBe('Anonymous');
  });

  it('should default roles to empty array when not present', () => {
    const token = jwt.sign({ sub: 'user-5' }, JWT_SECRET);
    const socket = createMockSocket({
      handshake: {
        auth: { token },
        headers: {},
      },
    });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    expect((socket as AuthenticatedSocket).user!.roles).toEqual([]);
  });

  it('should prefer auth token over authorization header', () => {
    const authToken = jwt.sign({ sub: 'from-auth' }, JWT_SECRET);
    const headerToken = jwt.sign({ sub: 'from-header' }, JWT_SECRET);
    const socket = createMockSocket({
      handshake: {
        auth: { token: authToken },
        headers: { authorization: `Bearer ${headerToken}` },
      },
    });
    const next = jest.fn();

    middleware(socket, next);

    expect(next).toHaveBeenCalledWith();
    expect((socket as AuthenticatedSocket).user!.userId).toBe('from-auth');
  });
});

describe('extractUserFromSocket', () => {
  it('should return user when socket is authenticated', () => {
    const socket = createMockSocket() as AuthenticatedSocket;
    socket.user = {
      userId: 'user-1',
      email: 'alice@test.com',
      displayName: 'Alice',
      roles: ['USER'],
    };

    const result = extractUserFromSocket(socket);
    expect(result.userId).toBe('user-1');
    expect(result.email).toBe('alice@test.com');
  });

  it('should return anonymous user when socket has no user', () => {
    const socket = createMockSocket();

    const result = extractUserFromSocket(socket);
    expect(result.userId).toBe('anon-socket-123');
    expect(result.displayName).toBe('Anonymous');
    expect(result.email).toBe('');
    expect(result.roles).toEqual([]);
  });
});
