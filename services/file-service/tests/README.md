# File-service integration tests

The health test runs without external services. The LocalStack/Redis tests are
gated by `AWS_ENDPOINT_URL` and `REDIS_URL`.

Start LocalStack and Redis, then run:

```sh
AWS_ENDPOINT_URL=http://localhost:4566 \
REDIS_URL=redis://localhost:6379 \
AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test cargo test -- --nocapture
```

The integration suite uses separate `*-test` DynamoDB tables and the
`otterworks-files-test` bucket.
