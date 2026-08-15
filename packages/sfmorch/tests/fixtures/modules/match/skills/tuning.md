# Tuning — FakeMatcher

A fixture, not a real matcher. This file exists because the module declares a
diagnostic with a `see_also`, and `sfm_smoke_test` checks that such a pointer
resolves — a fixture that cannot pass its own contract check is not a useful
fixture for testing that check.

## `inlier_yield` below 0.15

The `weak_matching` alarm. It declares `metric: inlier_yield`, whose healthy band
starts at 0.15, and the adapter raises it below the same number — which is the
agreement `sfm_smoke_test` verifies.

Raise `keep_ratio`.
