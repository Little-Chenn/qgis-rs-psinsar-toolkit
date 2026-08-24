# Security policy

## Supported version

Only the latest published version will be eligible for security fixes after the
project becomes public. The current `0.3.0-rc1` tree is an unpublished local
pre-release candidate.

## Reporting

Do not open a public issue for a suspected vulnerability involving arbitrary
file access, path traversal, unsafe archive handling, data overwrite, or code
execution. Use the repository's private security-advisory channel after the
public repository is created. A public security contact must be added before
publication. During local preparation, private reports may be sent to
`cyang5533@gmail.com`.

## Current security posture

- no network client or telemetry code;
- no automatic package installation;
- no subprocess or shell-command execution;
- no dynamic `eval`/`exec` on user content;
- input datasets are opened read-only where the workflow contract requires it;
- outputs use isolated, non-overwriting run directories.
