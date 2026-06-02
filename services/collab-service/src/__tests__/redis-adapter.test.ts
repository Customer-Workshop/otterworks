import Redis from 'ioredis';
import { RedisAdapter, type RedisConfig } from '../services/redis-adapter';

jest.mock('ioredis');

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

const testConfig: RedisConfig = {
  host: 'localhost',
  port: 6379,
  keyPrefix: 'test:',
};

describe('RedisAdapter', () => {
  let adapter: RedisAdapter;
  let mockClient: any;

  beforeEach(() => {
    jest.clearAllMocks();

    mockClient = {
      getBuffer: jest.fn().mockResolvedValue(null),
      set: jest.fn().mockResolvedValue('OK'),
      setex: jest.fn().mockResolvedValue('OK'),
      del: jest.fn().mockResolvedValue(1),
      hset: jest.fn().mockResolvedValue(1),
      hget: jest.fn().mockResolvedValue(null),
      hgetall: jest.fn().mockResolvedValue({}),
      hdel: jest.fn().mockResolvedValue(1),
      hincrby: jest.fn().mockResolvedValue(1),
      lpush: jest.fn().mockResolvedValue(1),
      lrange: jest.fn().mockResolvedValue([]),
      ltrim: jest.fn().mockResolvedValue('OK'),
      llen: jest.fn().mockResolvedValue(0),
      expire: jest.fn().mockResolvedValue(1),
      publish: jest.fn().mockResolvedValue(1),
      subscribe: jest.fn().mockResolvedValue(undefined),
      on: jest.fn(),
      ping: jest.fn().mockResolvedValue('PONG'),
      connect: jest.fn().mockResolvedValue(undefined),
      disconnect: jest.fn(),
    };

    (Redis as unknown as jest.Mock).mockImplementation(() => mockClient);

    adapter = new RedisAdapter(testConfig, mockLogger);
  });

  describe('key prefixing', () => {
    it('should prefix keys in get', async () => {
      await adapter.get('my-key');
      expect(mockClient.getBuffer).toHaveBeenCalledWith('test:my-key');
    });

    it('should prefix keys in set', async () => {
      const buf = Buffer.from('value');
      await adapter.set('my-key', buf);
      expect(mockClient.set).toHaveBeenCalledWith('test:my-key', buf);
    });

    it('should prefix keys in set with ttl', async () => {
      const buf = Buffer.from('value');
      await adapter.set('my-key', buf, 300);
      expect(mockClient.setex).toHaveBeenCalledWith('test:my-key', 300, buf);
    });

    it('should prefix keys in del', async () => {
      await adapter.del('my-key');
      expect(mockClient.del).toHaveBeenCalledWith('test:my-key');
    });
  });

  describe('hash operations', () => {
    it('should hset with prefix', async () => {
      await adapter.hset('myhash', 'field1', 'value1');
      expect(mockClient.hset).toHaveBeenCalledWith('test:myhash', 'field1', 'value1');
    });

    it('should hget with prefix', async () => {
      mockClient.hget.mockResolvedValue('stored-value');
      const result = await adapter.hget('myhash', 'field1');
      expect(mockClient.hget).toHaveBeenCalledWith('test:myhash', 'field1');
      expect(result).toBe('stored-value');
    });

    it('should hgetall with prefix', async () => {
      mockClient.hgetall.mockResolvedValue({ a: '1', b: '2' });
      const result = await adapter.hgetall('myhash');
      expect(mockClient.hgetall).toHaveBeenCalledWith('test:myhash');
      expect(result).toEqual({ a: '1', b: '2' });
    });

    it('should hdel with prefix', async () => {
      await adapter.hdel('myhash', 'field1');
      expect(mockClient.hdel).toHaveBeenCalledWith('test:myhash', 'field1');
    });

    it('should hincrby with prefix', async () => {
      mockClient.hincrby.mockResolvedValue(5);
      const result = await adapter.hincrby('myhash', 'counter', 1);
      expect(mockClient.hincrby).toHaveBeenCalledWith('test:myhash', 'counter', 1);
      expect(result).toBe(5);
    });
  });

  describe('list operations', () => {
    it('should lpush with prefix', async () => {
      await adapter.lpush('mylist', 'item');
      expect(mockClient.lpush).toHaveBeenCalledWith('test:mylist', 'item');
    });

    it('should lrange with prefix', async () => {
      mockClient.lrange.mockResolvedValue(['a', 'b', 'c']);
      const result = await adapter.lrange('mylist', 0, -1);
      expect(mockClient.lrange).toHaveBeenCalledWith('test:mylist', 0, -1);
      expect(result).toEqual(['a', 'b', 'c']);
    });

    it('should ltrim with prefix', async () => {
      await adapter.ltrim('mylist', 0, 99);
      expect(mockClient.ltrim).toHaveBeenCalledWith('test:mylist', 0, 99);
    });

    it('should llen with prefix', async () => {
      mockClient.llen.mockResolvedValue(10);
      const result = await adapter.llen('mylist');
      expect(mockClient.llen).toHaveBeenCalledWith('test:mylist');
      expect(result).toBe(10);
    });
  });

  describe('utility operations', () => {
    it('should expire with prefix', async () => {
      await adapter.expire('my-key', 60);
      expect(mockClient.expire).toHaveBeenCalledWith('test:my-key', 60);
    });

    it('should publish message', async () => {
      await adapter.publish('my-channel', 'message');
      expect(mockClient.publish).toHaveBeenCalledWith('my-channel', 'message');
    });

    it('should ping and return true', async () => {
      const result = await adapter.ping();
      expect(mockClient.ping).toHaveBeenCalled();
      expect(result).toBe(true);
    });

    it('should return false on ping failure', async () => {
      mockClient.ping.mockRejectedValue(new Error('connection lost'));
      const result = await adapter.ping();
      expect(result).toBe(false);
    });
  });

  describe('constructor', () => {
    it('should use empty prefix when not configured', () => {
      const noPrefixConfig: RedisConfig = { host: 'localhost', port: 6379 };
      const noPrefixAdapter = new RedisAdapter(noPrefixConfig);
      // Adapter created without error
      expect(noPrefixAdapter).toBeDefined();
    });

    it('should register error handlers', () => {
      expect(mockClient.on).toHaveBeenCalledWith('error', expect.any(Function));
      expect(mockClient.on).toHaveBeenCalledWith('connect', expect.any(Function));
    });
  });

  describe('connect', () => {
    it('should connect both client and subscriber', async () => {
      await adapter.connect();
      expect(mockClient.connect).toHaveBeenCalledTimes(2);
    });
  });

  describe('disconnect', () => {
    it('should disconnect both client and subscriber', () => {
      adapter.disconnect();
      expect(mockClient.disconnect).toHaveBeenCalledTimes(2);
    });
  });

  describe('getClient / getSubscriber', () => {
    it('should return the underlying redis client', () => {
      expect(adapter.getClient()).toBeDefined();
    });

    it('should return the underlying subscriber', () => {
      expect(adapter.getSubscriber()).toBeDefined();
    });
  });
});
