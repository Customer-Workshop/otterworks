import jwt from 'jsonwebtoken';
import { loadConfig } from '../config';
import {
  createAuthMiddleware,
  extractUserFromSocket,
  type AuthenticatedSocket,
} from '../middleware/auth';

const logger = {
  debug: jest.fn(),
  warn: jest.fn(),
} as never;

describe('collab configuration', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  it('loads defaults when environment variables are absent', () => {
    delete process.env.HTTP_PORT;
    delete process.env.REDIS_HOST;
    delete process.env.CORS_ORIGINS;

    expect(loadConfig()).toMatchObject({
      httpPort: 8084,
      redis: { host: 'localhost', port: 6379, keyPrefix: 'collab:' },
      cors: { origins: ['http://localhost:3000', 'http://localhost:4200'] },
      otel: { enabled: false, serviceName: 'collab-service' },
    });
  });

  it('parses configured values and comma-separated origins', () => {
    process.env.HTTP_PORT = '9090';
    process.env.REDIS_PORT = '6380';
    process.env.CORS_ORIGINS = 'https://one.example,https://two.example';
    process.env.OTEL_ENABLED = 'true';

    expect(loadConfig()).toMatchObject({
      httpPort: 9090,
      redis: { port: 6380 },
      cors: { origins: ['https://one.example', 'https://two.example'] },
      otel: { enabled: true },
    });
  });
});

describe('socket authentication', () => {
  beforeEach(() => jest.clearAllMocks());

  it('authenticates a token and maps its claims to the socket user', () => {
    const token = jwt.sign(
      {
        sub: 'user-1',
        email: 'user@example.com',
        display_name: 'User One',
        roles: ['editor'],
      },
      'secret', // nosemgrep: javascript.jsonwebtoken.security.jwt-hardcode.hardcoded-jwt-secret
    );
    const socket = {
      id: 'socket-1',
      handshake: { auth: { token }, headers: {} },
    } as unknown as AuthenticatedSocket;
    const next = jest.fn();

    createAuthMiddleware('secret', logger)(socket, next);

    expect(next).toHaveBeenCalledWith();
    expect(socket.user).toEqual({
      userId: 'user-1',
      email: 'user@example.com',
      displayName: 'User One',
      roles: ['editor'],
    });
  });

  it('rejects missing and invalid tokens', () => {
    const nextMissing = jest.fn();
    const socket = {
      id: 'socket-1',
      handshake: { auth: {}, headers: {} },
    } as never;
    createAuthMiddleware('secret', logger)(socket, nextMissing);
    expect(nextMissing.mock.calls[0][0]).toEqual(new Error('Authentication required'));

    const nextInvalid = jest.fn();
    const invalidSocket = {
      id: 'socket-2',
      handshake: { auth: { token: 'invalid' }, headers: {} },
    } as never;
    createAuthMiddleware('secret', logger)(invalidSocket, nextInvalid);
    expect(nextInvalid.mock.calls[0][0]).toEqual(new Error('Invalid or expired token'));
  });

  it('extracts an anonymous fallback when no user is attached', () => {
    expect(extractUserFromSocket({ id: 'socket-9' } as never)).toEqual({
      userId: 'anon-socket-9',
      email: '',
      displayName: 'Anonymous',
      roles: [],
    });
  });
});
