# Claude Code execution adapter

Follow `README.md` as the operational entry point. Use isolated subagents for
task packets marked independent, while retaining single-writer ownership of
shared state. Continue until `research_control release` passes or a concrete
external-access blocker is recorded. The preserved legacy prompt is not normal
runtime context.
