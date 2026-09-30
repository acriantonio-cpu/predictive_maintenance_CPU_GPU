# Governance

> English copy of [`GOVERNANCE.md`](../../GOVERNANCE.md) (Italian); keep them in sync.

## Roles

- **Lead maintainer**: @Antonio (author of the specification). Decides on roadmap, releases and
  diagnosis rules.
- **Second maintainer**: to be identified by release 0.1 (succession plan: requirement 15.8). Has
  merge and release rights.
- **Contributors**: anyone who opens issues or pull requests.

## Decisions

- Ordinary changes go through a pull request with at least one review and green CI.
- Changes to the method (default thresholds, diagnosis rules, indicators) require a note in
  `docs/metodologia.md` and `docs/en/methodology.md` with the rationale and, if possible, the
  results on the simulator or on real data.
- In case of disagreement the lead maintainer decides, giving reasons in writing in the PR.

## Relations with upstream projects

LibreHardwareMonitor (MPL-2.0), nvidia-ml-py, smartmontools: problems found in the sensors are
reported upstream; HWDrift does not redistribute third-party binaries.

## Code of conduct

[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
