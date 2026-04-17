# Shared Protocol Buffers

This directory contains shared protobuf definitions for inter-service
gRPC communication (future consideration).

## Structure

```
proto/
  user/         - User-related message types
  file/         - File metadata and operations
  document/     - Document CRUD operations
  notification/ - Notification event types
```

## Usage

Services currently communicate via REST/HTTP. gRPC definitions here
serve as a future migration path for high-throughput internal service
communication.
