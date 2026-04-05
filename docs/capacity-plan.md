# Capacity plan

## Current measured results

| tier   | profile               | p95 latency | error rate | request rate |
| ------ | --------------------- | ----------: | ---------: | -----------: |
| bronze | 50 users              |    86.20 ms |      0.00% | 457.26 req/s |
| silver | up to 200 users       |   400.50 ms |      0.30% | 431.68 req/s |
| gold   | stress profile (120s) |    11.96 ms |      0.00% |  99.28 req/s |

## Assumptions

- traffic goes through nginx to 3 Flask app containers
- Redis can reduce read load for resolve traffic, read hits on popular short codes are greatly improved by cache
- each successful resolve still writes a click event to PostgreSQL

## Practical limit statement

Based on current evidence, the stack handles up to 200 concurrent users with low error rate and sub-second p95 in the silver profile.

The first pressure point is PostgreSQL write load from event creation on high resolve traffic. A message queue could be added to offload this work and allow higher sustained traffic. Or more replicas of the database to be eventually consistent, however there is the possibility of a cache miss incurring higher latency if the read goes to a replica that is not yet up to date.

## What to scale first

1. Keep Redis enabled.
2. Increase app replicas behind nginx if CPU saturates.
3. Tune PostgreSQL resources and connections.
4. Move click writes to async processing for higher sustained traffic.
