# Dependency Notes — collab-service

| Package | Version | Reason | Tracking |
|---------|---------|--------|----------|
| lodash | ^4.18.1 | Upgraded from the previous 4.17.20 pin to remediate high-severity advisories (GHSA-35jh-r3h4-6jhm command injection, GHSA-r5fr-rjxr-66jc code injection, GHSA-f23m-r3pf-42rh prototype pollution); no fix exists within 4.17.x (advisories cover <=4.17.23). lodash is not imported anywhere in src/, so the former DEPS-301 legacy-compatibility pin no longer applies. | DEPS-301 |
