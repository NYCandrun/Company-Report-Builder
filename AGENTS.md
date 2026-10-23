# Agent execution adapter

Follow `README.md` as the operational entry point. Continue autonomously from
the supplied company URL through release acceptance. Use subagents for task
packets marked independent when the runtime provides them. Do not read the
legacy prompt during normal work, do not skip a failed control, and do not
claim completion without a passing release manifest.

When repository instructions and a task packet differ, stop that task and
report the conflict to the orchestrator; unrelated work may continue.
