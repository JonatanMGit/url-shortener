# Decision log

This file records architecture choices and constraints for the project.

## Required constraints: Flask and PostgreSQL

Flask and PostgreSQL were required by the project template and evaluator expectations.
They were not optional architecture choices.

- Flask is the required web framework for routes and API handling.
- PostgreSQL is the required persistent database used by local and CI test flows.

All other decisions were made around these two constraints.

## DigitalOcean platform decision

DigitalOcean was chosen for deployment because it offers a straightforward path from local containers to a scalable production setup.

- supports container-based deployments and managed infrastructure with low setup overhead
- supports edge caching through CDN, which can cache redirect responses (including `302` when cache rules and response headers allow it)
- edge-served redirects reduce repeated origin hits, lowering load on nginx, Flask containers, and PostgreSQL for hot links
- supports horizontal scaling by increasing app container replicas behind a load balancer (preferred for this stateless API layer)
- supports vertical scaling by increasing compute resources for app nodes and stateful components when needed

Tradeoff:

- redirect edge caching can reduce origin-side click event accuracy if requests are served without reaching the app
- to preserve analytics quality, cache policies should be applied selectively or paired with edge-side analytics logs
- managed platform convenience may cost more than self-hosted infrastructure at large sustained scale

## Redis decision

Redis was chosen as a fast in-memory datastore to cache database-backed resolve data.

The URL shortener workload is read-heavy and write-light: short links are created less often than they are resolved.
Caching frequent resolve lookups in Redis reduces repeated PostgreSQL reads and improves latency on hot links.

Tradeoff:

- extra service to deploy, monitor, and keep healthy
- cache invalidation must be handled carefully on updates/deletes

## Prometheus and Grafana decision

Prometheus and Grafana were chosen for observability with low operational overhead.

- Prometheus scrapes and stores time-series metrics.
- Grafana provides dashboards for fast analysis.
- Together they make it easier to detect and investigate issues, including when one Flask instance crashes.

Tradeoff:

- additional resource usage compared to app-only deployments
- extra monitoring configuration to maintain

## Alertmanager decision

Alertmanager was chosen because it integrates directly with Prometheus and provides ready-made routing for notifications.

- supports common notification channels without building custom notifier code
- handles deduplication, grouping, and routing policies for alerts
- fits naturally into the existing observability stack

Tradeoff:

- another operational component to configure and maintain
