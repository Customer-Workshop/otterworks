-- Drop everything the monolith owns (which is everything) so schema.sql + seed.sql rebuild it.
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
