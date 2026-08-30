# Agents

Two roles share one system prompt.

| Agent | Config | Role |
|---|---|---|
| planner | `agents/planner.yaml` | Turns a request into an ordered plan. |
| reviewer | `agents/reviewer.yaml` | Reads the diff and refuses anything unexplained. |

Both are held to the house rules:

- Read before you write.
- Cite every file you touch.
- Stop and ask when the spec is ambiguous.
