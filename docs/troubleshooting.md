# Troubleshooting guide

Use this file as the "if X happens, try Y" reference.

## Quick checks

```bash
docker compose -f docker-compose.production.yml ps
docker compose -f docker-compose.production.yml logs app1 --tail 200
docker compose -f docker-compose.production.yml logs nginx --tail 200
docker compose -f docker-compose.production.yml logs postgres --tail 200
```

```bash
curl http://localhost:5000/health
curl http://localhost:5000/metrics
curl http://localhost:5000/metrics/prometheus
```

## If X, try Y

| if you see                                      | try this                                                                           |
| ----------------------------------------------- | ---------------------------------------------------------------------------------- |
| `FATAL: database "hackathon_db" does not exist` | wait a few seconds for postgres startup, then retry; verify `.env` database values |
| `Cannot use uninitialized Proxy`                | check that postgres is up and app env values are loaded                            |
| exact duplicate `POST /users` returns `422`     | update/rebuild to current code; expected behavior is idempotent `201`              |
| conflicts after `/users/bulk` import            | run latest code that realigns `users.id` sequence                                  |
| `/r/<code>` returns `410`                       | URL is inactive; set `is_active=true` via `PUT /urls/<id>`                         |
| `/r/<code>` returns `404`                       | short code does not exist; verify code and path                                    |
| cache never hits                                | set `REDIS_ENABLED=true`, check `REDIS_URL`, verify redis container                |
| grafana login fails                             | check `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD` in `.env`                  |

## Bugs fixed during this project

- Duplicate user handling: exact duplicate payload now returns `201` with the existing user.
- Missing delete handlers: `DELETE /users/<id>` and `DELETE /urls/<id>` now return `204`.
- Redirect coverage: both `/r/<short_code>` and `/urls/<short_code>/redirect` are available.
- Sequence drift after bulk load: sequence reset logic added for `users.id`.

## Escalation rule

Use [runbooks.md](runbooks.md) if:

- service down alert stays active for more than 5 minutes
- high error rate alert stays active after first mitigation
- database failure impacts all app replicas
