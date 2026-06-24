# TEA Orchestrator — specialist agents (Codex roster)

These reusable, **read-only** specialist roles are spawned by the `tea` skill
(the TEA orchestrator). Their canonical definitions (with frontmatter and the full role contract)
live in `.claude/agents/tea-*.md` and are platform-neutral — a Codex runtime
should load the matching file for the full brief. This roster is the index.

| Role | File | When spawned | Returns |
|---|---|---|---|
| Materials analyst | `.claude/agents/tea-materials-analyst.md` | One per supplied file/model, during intake | Structured summary: candidate inputs (required vs supplied), formulas, units gaps |
| Schema / compatibility reviewer | `.claude/agents/tea-schema-reviewer.md` | Before the starting-document approval gate | Validator result + mechanical/compatibility findings with smallest fixes |
| Research / source-screening worker | `.claude/agents/tea-research-screener.md` | Per entity or coverage slice each research round | Candidate source JSON (context-free for reference values) |
| Source extractor | `.claude/agents/tea-source-extractor.md` | Per (source, coverage-slice) | Extractor JSON: raw values + provenance + scope-relevance status, no math |
| Quality / completeness reviewer | `.claude/agents/tea-quality-reviewer.md` | Before completeness review or finalization | Coverage, gap routes, quality flags, ready-to-finalize |

Shared rules (full text in the canonical files and
`.claude/skills/tea/references/interaction-and-gates.md`):

- Read-only by default; workers may write only isolated staging outputs. The main
  orchestrator serializes all canonical writes (phase scripts + orchestrator CLI).
- Each worker returns its result as its value; the orchestrator validates the
  contract, retries once with a narrower prompt on failure, then falls back safely
  or surfaces the exact issue.
- Apply the material's sensitivity policy (`local-only` / `metadata-only` /
  `normal-processing`). Never put confidential content in web queries.
- Fan out per supplied file/model, source, extraction batch, entity, or option;
  announce meaningful fan-out and show progress in work units.
