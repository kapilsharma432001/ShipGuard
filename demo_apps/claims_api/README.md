# Claims API Demo App

This is a synthetic FastAPI-style Claims API used only to demonstrate
ShipGuard release-risk analysis. It does not contain real company or client
code.

## Baseline Behavior

- Clients submit claims with `claimant_id`.
- Claim decisions can return `Approved` or `Denied`.
- Responses include `assigned_queue`.
- Deployment config is represented by `.env.example` and `docker-compose.yml`.

## Local Demo

This app is intentionally small and not intended for production use.
