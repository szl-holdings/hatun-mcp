# Security Policy

> Doctrine v11 LOCKED · 749/14/163 · locked_at `c7c0ba17`

## Reporting a Vulnerability

Please report security vulnerabilities by email to **stephenlutar2@gmail.com**.

- We operate a **90-day coordinated disclosure window** from the date of acknowledgement.
- Please do not open public issues for security reports.
- We will acknowledge receipt within 3 business days.

## PGP

A PGP key for encrypted reports is being provisioned. _(Founder action: publish PGP public key fingerprint here.)_

## Supported Versions

The latest release on the default branch is supported. Older tags are best-effort.

## Verifying Releases (Sigstore / cosign)

SZL release artifacts are signed with **cosign keyless (OIDC)**. To verify:

```bash
cosign verify-blob \
  --certificate <artifact>.crt \
  --signature <artifact>.sig \
  --certificate-identity-regexp 'https://github.com/szl-holdings/hatun-mcp/.github/workflows/.+' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  <artifact>
```

SBOMs (SPDX JSON) are published per release and on the `attestations` branch.

## Compliance

See the organization compliance posture: <https://github.com/szl-holdings/compliance-posture>.
