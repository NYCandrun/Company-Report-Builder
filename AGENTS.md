# Codex execution adapter

Follow `README.md` as the operational entry point. Run `research_control run`
with the supplied company URL, dispatch every ready packet, and repeat until
exact-artifact release acceptance passes. Use subagents for packets marked
independent. Give each a unique worker ID, the packet only, and no inherited
status conversation. The SQLite scheduler—not the parent chat—determines the
task graph, retries, dependencies, and concurrency.

Do not ask the user for source, page, batch, or worker counts. Discovery ends by
documented channel saturation. Numeric limits are safety breakers and must
produce incomplete status when reached.

Do not read the legacy prompt during normal work, skip a failed control, edit
scheduler state directly, or claim completion without a passing release
manifest. When repository instructions and a packet conflict, block that packet
and report the conflict; unrelated ready work may continue.
