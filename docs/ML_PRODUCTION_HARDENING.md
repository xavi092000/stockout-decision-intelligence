# ML Production Hardening

The runtime policy is protected by a versioned feature contract shared by dataset generation, training, and inference.

## Startup validation

`MLDecisionPolicy` fails fast when the model or metadata is missing, malformed, uses a different feature schema, exposes a different feature order, or contains unsupported action classes.

## Runtime validation

Every inference row must contain exactly the expected columns in the expected order, one row only, no missing or non-finite values, and no negative stock, demand, pending-unit, lead-time, or surplus values.

## Operational metrics

`metrics_snapshot()` exposes model load duration, prediction totals, prediction errors, deterministic transfer fallbacks, average prediction latency, schema version, and action counts.

## Test isolation

`pytest.ini` restricts collection to `simulation/tests`, preventing accidental collection from Python caches, virtual environments, and third-party packages.
