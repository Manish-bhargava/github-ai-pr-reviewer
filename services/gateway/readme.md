github sends events to this gateway, and the gateway:

Receives GitHub webhooks.


Verifies the webhook is really from GitHub.
Rejects fake requests.
Forwards valid events to the internal webhook-processing service.


Exposes health checks.
Exposes Prometheus metrics for monitoring.