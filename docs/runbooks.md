# Runbooks

Alert rules are in `production/monitoring/prometheus/alerts.yml`.

## Runbook: UrlShortenerServiceDown

Trigger:

`up{job="url-shortener-app"} == 0` for 2 minutes.

Steps:

1. Check container state.

```bash
docker compose -f docker-compose.production.yml ps
```

2. Check app and nginx logs.

```bash
docker compose -f docker-compose.production.yml logs app1 app2 app3 --tail 200
docker compose -f docker-compose.production.yml logs nginx --tail 200
```

3. Check ingress health.

```bash
curl -i http://localhost:5000/health
```

4. Restart app containers.

```bash
docker compose -f docker-compose.production.yml restart app1 app2 app3
```

5. If DB errors are present, check postgres logs.

```bash
docker compose -f docker-compose.production.yml logs postgres --tail 200
```

Done when:

- `/health` returns 200
- app targets are UP in Prometheus
- alert resolves in Alertmanager

## Runbook: UrlShortenerHighErrorRate

Trigger:

5xx ratio above 5 percent for 5 minutes.

Steps:

1. Confirm alert in Grafana and Prometheus.
2. Pull recent app logs.

```bash
docker compose -f docker-compose.production.yml logs app1 app2 app3 --tail 300
```

3. Identify the main failure source:

- DB errors
- payload/validation spikes
- one bad replica
- host resource limits

4. Apply mitigation:

- one bad replica: restart that replica
- DB issue: recover postgres
- release issue: rollback using [deploy-guide.md](deploy-guide.md)

5. Validate:

```bash
curl http://localhost:5000/health
curl http://localhost:5000/metrics
```

Done when:

- 5xx ratio falls below threshold
- alert resolves

## Simulated incident root cause

Incident summary:

- Alert: `UrlShortenerHighErrorRate`
- Symptom: elevated 5xx after a fresh deploy
- Scope: all three app containers behind nginx

What happened:

- One of the app replicas failed to complete database initialization during startup, causing it to crash.

How we confirmed it:

- `docker compose ... ps` showed unstable app container health.
- app logs showed database init failures.

Fix:

- stack was redeployed.

Prevention:

- keep startup ordering in production compose
- keep health checks enabled
- run smoke checks after each deploy
