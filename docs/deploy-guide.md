# Deploy guide

This guide is for the production compose stack in `docker-compose.production.yml`.

## What runs

- `nginx`
- `app1`, `app2`, `app3`
- `postgres`
- `redis`
- `prometheus`, `grafana`, `alertmanager`

## Deploy or update

Copy env file:

```bash
cp .env.example .env
```

Set at least:

- `DATABASE_NAME`
- `DATABASE_USER`
- `DATABASE_PASSWORD`
- `GRAFANA_ADMIN_USER`
- `GRAFANA_ADMIN_PASSWORD`

Bring up the stack:

```bash
docker compose -f docker-compose.production.yml up -d --build
```

Check status:

```bash
docker compose -f docker-compose.production.yml ps
```

Basic checks:

```bash
curl http://localhost:5000/health
curl http://localhost:5000/metrics
curl http://localhost:5000/metrics/prometheus
```

## Rollback

Move to a known good commit and rebuild:

```bash
docker compose -f docker-compose.production.yml down
git fetch --all
git checkout <known_good_commit_sha>
docker compose -f docker-compose.production.yml up -d --build
```

Check health again.

Return to latest main when ready:

```bash
git checkout main
git pull
docker compose -f docker-compose.production.yml up -d --build
```

## Restart only

If rollback is not needed:

```bash
docker compose -f docker-compose.production.yml restart app1 app2 app3 nginx
```

If you also need to reset backing services:

```bash
docker compose -f docker-compose.production.yml down
docker compose -f docker-compose.production.yml up -d
```
