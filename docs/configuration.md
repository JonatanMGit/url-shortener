# Configuration

Canonical template: `.env.example`

## Environment variables

| variable                  | default                                       | required              | purpose                  |
| ------------------------- | --------------------------------------------- | --------------------- | ------------------------ |
| `FLASK_DEBUG`             | `false`                                       | no                    | Flask debug mode         |
| `DATABASE_NAME`           | `hackathon_db`                                | yes                   | PostgreSQL database name |
| `DATABASE_HOST`           | `localhost`                                   | yes                   | PostgreSQL host          |
| `DATABASE_PORT`           | `5432`                                        | yes                   | PostgreSQL port          |
| `DATABASE_USER`           | `postgres`                                    | yes                   | PostgreSQL user          |
| `DATABASE_PASSWORD`       | `postgres`                                    | yes                   | PostgreSQL password      |
| `REDIS_ENABLED`           | `false` locally, `true` in production compose | no                    | turns Redis cache on/off |
| `REDIS_URL`               | `redis://localhost:6379/0`                    | when Redis is enabled | Redis connection string  |
| `REDIS_CACHE_TTL_SECONDS` | `300`                                         | no                    | cache TTL                |
| `REDIS_CACHE_KEY_PREFIX`  | `url-shortener`                               | no                    | cache key prefix         |
| `LOG_LEVEL`               | `INFO`                                        | no                    | app log level            |
| `LOG_FILE_PATH`           | empty                                         | no                    | optional log file path   |
| `GRAFANA_ADMIN_USER`      | `admin`                                       | production stack      | Grafana login user       |
| `GRAFANA_ADMIN_PASSWORD`  | `admin`                                       | production stack      | Grafana login password   |

## Local sample

```env
FLASK_DEBUG=true
DATABASE_NAME=hackathon_db
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres

REDIS_ENABLED=false
REDIS_URL=redis://localhost:6379/0
REDIS_CACHE_TTL_SECONDS=300
REDIS_CACHE_KEY_PREFIX=url-shortener

LOG_LEVEL=INFO
LOG_FILE_PATH=

GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
```
