import express from 'express';
import { createServer } from 'http';
import { Server as SocketIOServer } from 'socket.io';
import cors from 'cors';
import helmet from 'helmet';
import { createLogger, format, transports } from 'winston';
import { setupCollaborationHandlers } from './handlers/collaboration';
import { RedisAdapter } from './services/redis-adapter';
import { DocumentStore } from './services/document-store';

const logger = createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: format.combine(
    format.timestamp(),
    format.json(),
  ),
  defaultMeta: { service: 'collab-service' },
  transports: [new transports.Console()],
});

const app = express();
const httpServer = createServer(app);

// Middleware
app.use(helmet());
app.use(cors({
  origin: ['http://localhost:3000', 'http://localhost:4200'],
  credentials: true,
}));
app.use(express.json());

// Health check
app.get('/health', (_req, res) => {
  res.json({ status: 'healthy', service: 'collab-service' });
});

// Metrics endpoint
app.get('/metrics', (_req, res) => {
  res.type('text/plain').send(
    '# HELP collab_service_up Collaboration Service is running\n' +
    '# TYPE collab_service_up gauge\ncollab_service_up 1\n' +
    '# HELP collab_active_connections Current WebSocket connections\n' +
    '# TYPE collab_active_connections gauge\n' +
    `collab_active_connections ${io.engine.clientsCount}\n`
  );
});

// Active documents endpoint
app.get('/api/v1/collab/documents', (_req, res) => {
  const rooms = io.sockets.adapter.rooms;
  const activeDocuments: string[] = [];
  rooms.forEach((_sockets, room) => {
    if (room.startsWith('doc:')) {
      activeDocuments.push(room.replace('doc:', ''));
    }
  });
  res.json({ activeDocuments, count: activeDocuments.length });
});

// Socket.IO server
const io = new SocketIOServer(httpServer, {
  cors: {
    origin: ['http://localhost:3000', 'http://localhost:4200'],
    credentials: true,
  },
  pingInterval: 25000,
  pingTimeout: 20000,
});

// Initialize services
const redisHost = process.env.REDIS_HOST || 'localhost';
const redisPort = parseInt(process.env.REDIS_PORT || '6379', 10);
const redisAdapter = new RedisAdapter(redisHost, redisPort);
const documentStore = new DocumentStore(redisAdapter);

// Setup WebSocket handlers
setupCollaborationHandlers(io, documentStore, logger);

// Start server
const HTTP_PORT = parseInt(process.env.HTTP_PORT || '8084', 10);

httpServer.listen(HTTP_PORT, '0.0.0.0', () => {
  logger.info(`Collaboration Service listening on port ${HTTP_PORT}`);
});

process.on('SIGTERM', () => {
  logger.info('SIGTERM received, shutting down...');
  httpServer.close(() => {
    redisAdapter.disconnect();
    process.exit(0);
  });
});
