# Status

Delivery status is generated from `specs/*/status.json`. The spec-delivery page rebuilds on each push to main.

| State | Meaning |
|---|---|
| SPECIFIED | The requirement is written. |
| LANDED | The change is on main. |
| VERIFIED | The change is on main with a bound test. |
| RETIRED | The requirement is withdrawn. |

The active spec is `specs/terminal-runtime`.
