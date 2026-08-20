// Generates the local-development fixture consumed by AuthService.mockLogin().
//
// The admin dashboard has no real login endpoint yet, so it mints a JWT for the
// seeded admin user. That JWT is verified for real by admin-service, so it has
// to be signed with the same JWT_SECRET docker-compose hands the backends. The
// fixture is generated here instead of being committed so no credential lives
// in source; the defaults below mirror docker-compose.yml, so a plain
// `npm install` / `npm start` produces the same token local dev has always used.
import { createHmac } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const JWT_SECRET =
  process.env.JWT_SECRET || 'otterworks-local-dev-jwt-secret-change-me-in-production';
const USER_ID = process.env.OW_DEV_ADMIN_USER_ID || 'a0000000-0000-0000-0000-000000000001';
const EMAIL = process.env.OW_DEV_ADMIN_EMAIL || 'admin@otterworks.dev';
const ROLE = process.env.OW_DEV_ADMIN_ROLE || 'admin';
const DISPLAY_NAME = process.env.OW_DEV_ADMIN_DISPLAY_NAME || 'Admin User';
const ISSUED_AT = Number(process.env.OW_DEV_ADMIN_IAT || 1704067200);
const EXPIRES_AT = Number(process.env.OW_DEV_ADMIN_EXP || 1924905600);

const encode = value => Buffer.from(JSON.stringify(value)).toString('base64url');

const header = encode({ alg: 'HS256', typ: 'JWT' });
const payload = encode({
  sub: USER_ID,
  user_id: USER_ID,
  email: EMAIL,
  role: ROLE,
  iat: ISSUED_AT,
  exp: EXPIRES_AT,
});
const signature = createHmac('sha256', JWT_SECRET).update(`${header}.${payload}`).digest('base64url');

const outputPath = join(
  dirname(fileURLToPath(import.meta.url)),
  '..',
  'src',
  'app',
  'core',
  'fixtures',
  'dev-mock-auth.json'
);

mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(
  outputPath,
  `${JSON.stringify(
    {
      _generated: 'scripts/gen-dev-mock-auth.mjs - local development fixture, not committed',
      userId: USER_ID,
      displayName: DISPLAY_NAME,
      role: ROLE,
      token: `${header}.${payload}.${signature}`,
    },
    null,
    2
  )}\n`
);
