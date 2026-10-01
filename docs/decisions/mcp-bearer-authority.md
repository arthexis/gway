# MCP bearer authority

The remote/MCP authorization surface is derived from the bearer linked by the
operator, not from a ChatGPT-specific permission bundle.

## Contract

- Any valid Gway bearer may be linked by the remote browser flow.
- `chatgpt-actions` and `chatgpt-logs` are legacy scope names, not integration
  prerequisites.
- The linked bearer is the absolute authority ceiling for OAuth grants and the
  resulting MCP operation surface.
- When the client does not deliberately request narrower authority, consent
  inherits the bearer's current exact and union scopes.
- Exact and union authority are both preserved through the OAuth grant.
- A remote connection never gains authority that is absent from the linked
  bearer.
- `security token rename OLD NEW` changes only the human-readable token name;
  bearer secret/public ID, bindings, expiry/disabled state, usage history and
  OAuth links continue to refer to the same stable token identity.

The implementation and acceptance coverage for this contract live in PR #1380.
