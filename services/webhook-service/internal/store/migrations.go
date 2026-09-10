package store

import "embed"

// MigrationFS contains the webhook schema migrations.
//
//go:embed migrations/*.sql
var MigrationFS embed.FS
