# Security Hardening Report

## Initial Findings

- ASGI static responses must consistently include frame, content-type, referrer, permissions, and CSP headers.
- Production must fail closed when SPA dist assets are missing and must never serve `/src/main.tsx`.
- Missing `/app/assets/*` files must return 404 rather than the SPA shell.
- SVG upload is not allowed because inline script and XML behaviors create XSS and content-sniffing risk.
- Session cookies must remain HttpOnly, SameSite at least Lax, and Secure under HTTPS production URLs.
- CSRF cookies may be readable by the frontend, but must remain SameSite protected and Secure under HTTPS production URLs.
- Data Lab Agent trusted Python execution is not a sandbox and must remain disabled in ordinary production deployments.

## Completed Controls

- Static ASGI short-circuit responses use a restrictive baseline CSP and standard browser hardening headers.
- `/api/health` probe responses are covered by the same ASGI hardening headers.
- The `/provider-center` fallback page was simplified so the strict CSP does not require inline styles.
- Source SPA fallback is restricted to development/test environments with explicit opt-in.
- Missing SPA/public assets return 404 instead of the SPA shell.
- SVG upload support has been removed from upload kind, extension, and MIME allowlists.
- SVG assets are no longer emitted as multimodal inline image attachments; first-party favicon SVG remains a static packaged asset only.
- Session and CSRF cookie flags are covered for HTTP test mode and HTTPS production base URLs.
- Data Lab Agent public risk summaries state `sandbox_claim=none` and omit local session paths from public session payloads.
- Data Lab model preflight and reproducibility manifest work reduce workflow ambiguity before outputs are treated as reliable.

## Open Review Items

- Trusted execution remains unsafe without an isolated worker or container.
- Data Lab model tests verify reasonableness, not publication-grade statistical validity.
- Optimization suites remain compute-sensitive and must keep backend resource caps enabled.
