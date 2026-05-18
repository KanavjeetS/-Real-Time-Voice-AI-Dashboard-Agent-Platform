# Documentation

Technical documentation for **AI Calling Agent**.

## Architecture & design

| Document | Description |
|----------|-------------|
| **[ARCHITECTURE.md](./ARCHITECTURE.md)** | Full technical architecture — context diagrams, 4-layer model, call lifecycle, data model, APIs, security |
| **[LATENCY.md](./LATENCY.md)** | Performance SLOs, metrics, optimization strategies |
| **[DEPLOYMENT.md](./DEPLOYMENT.md)** | Docker Compose, local dev, production checklist |
| **[VERCEL_DEPLOY.md](./VERCEL_DEPLOY.md)** | Vercel dashboard + Railway API deployment |

## Quick links

- Repository root: [../README.md](../README.md)
- Database DDL: [../scripts/init_db.sql](../scripts/init_db.sql)
- Environment template: [../.env.example](../.env.example)

## Diagram index (in ARCHITECTURE.md)

All diagrams use **Mermaid** (renders on GitHub):

1. System context — actors and external services  
2. Deployment topology — Vercel, Railway, Supabase, Redis, Twilio  
3. Four-layer logical architecture  
4. Outbound call sequence diagram  
5. Real-time voice pipeline flow  
6. Dialogue state machine  
7. Entity-relationship model  
8. Background job queue flow  
