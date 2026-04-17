import Redis from 'ioredis';

export class RedisAdapter {
  private client: Redis;
  private subscriber: Redis;

  constructor(host: string, port: number) {
    this.client = new Redis({ host, port, maxRetriesPerRequest: 3 });
    this.subscriber = new Redis({ host, port, maxRetriesPerRequest: 3 });

    this.client.on('error', (err) => console.error('Redis client error:', err));
    this.subscriber.on('error', (err) => console.error('Redis subscriber error:', err));
  }

  async get(key: string): Promise<Buffer | null> {
    return this.client.getBuffer(key);
  }

  async set(key: string, value: Buffer, ttlSeconds?: number): Promise<void> {
    if (ttlSeconds) {
      await this.client.setex(key, ttlSeconds, value);
    } else {
      await this.client.set(key, value);
    }
  }

  async del(key: string): Promise<void> {
    await this.client.del(key);
  }

  async publish(channel: string, message: string): Promise<void> {
    await this.client.publish(channel, message);
  }

  async subscribe(channel: string, callback: (message: string) => void): Promise<void> {
    await this.subscriber.subscribe(channel);
    this.subscriber.on('message', (ch, msg) => {
      if (ch === channel) callback(msg);
    });
  }

  disconnect(): void {
    this.client.disconnect();
    this.subscriber.disconnect();
  }
}
