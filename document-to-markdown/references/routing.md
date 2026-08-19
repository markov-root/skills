# Target routing guidance

The normal workflow lets `doc2md` choose a route from measured benchmark evidence.

## Profiles

| Profile    | Intended behavior                                                              |
| ---------- | ------------------------------------------------------------------------------ |
| `fast`     | Local, bounded extraction with inexpensive fallbacks.                          |
| `balanced` | Default: best measured local quality within resource budgets.                  |
| `fidelity` | Slower layout/OCR routes when the input warrants them.                         |
| `private`  | Forbid network fetches beyond the supplied URL and forbid external processors. |

Profiles describe policy and budgets. They do not permanently bind a format to a named dependency.

## Escalation rule

Escalate only when the current attempt produces a diagnosed reason:

- static HTML is thin or a client-rendered shell;
- PDF lacks a usable text layer or has broken reading order;
- table/formula/code structure is materially lost;
- the returned bytes contradict the declared type;
- the adapter errors, times out, exceeds memory, or violates a policy constraint.

Record every attempt. Do not discard a cheaper usable result merely because a more expensive route
exists.

## Generative extraction

Generative/VLM conversion is never the silent default. It requires:

1. explicit user or profile permission;
2. disclosure of provider, cost, and data egress;
3. a provenance tier distinct from extractive/OCR text;
4. post-conversion checks for unsupported invention;
5. a deterministic fallback or a clearly failed result.

See the project documentation for the full target ladders and benchmark policy.
