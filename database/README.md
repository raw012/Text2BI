# Database

The MVP defaults to SQLite for zero-configuration local startup. Set
`DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/text2bi` to use
PostgreSQL in production. SQLAlchemy creates the `datasets` and `dashboards`
tables at application startup.
