# Security Policy

## Supported Versions

We actively maintain the `main` branch of FamilyOS. Security fixes are applied to `main` and will be backported to maintained release branches as they are published.

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly so we can address it quickly:

- Submit a private report using the GitHub "Report a vulnerability" feature for this repository.
- Or email the maintainer team at [security@familyos.dev](mailto:security@familyos.dev).

Please include as much detail as possible (steps to reproduce, impact assessment, proposed mitigations) and do not disclose the issue publicly until we have released a fix.

## Coordinated Disclosure Process

1. We acknowledge receipt of the report within **48 hours** and begin investigation.
2. We work with you to understand and validate the issue.
3. We develop, test, and prepare a fix, including any necessary documentation.
4. We coordinate a release window and publish mitigation guidance.
5. We credit reporters in release notes if they opt in once the fix ships.

## Out of Scope

The following are out of scope for our security program:

- Social engineering attacks against project contributors or maintainers
- Attacks that rely on compromised user devices or networks outside the FamilyOS environment
- Denial of service attacks that require excessive resources unlikely to occur in production deployments

## Preferred Languages

We prefer vulnerability reports in English.

## Security Updates

Security-related changes will be announced in the release notes and documented in `docs/development/` as part of the relevant changelog or ADR. Subscribe to the repository releases to stay informed.
