TASK TYPE: EVIDENCE-BOUNDED ARCHITECTURE MODELING

Research is complete. Do not browse, search, fetch sources, or add outside
facts. Work only from the packet's reviewed synthesis, verified fact records,
source manifest, verification results, timelines, and design reference. A
company name or a familiar industry pattern is not evidence.

Reconstruct the minimum logical architecture necessary to explain documented
behavior. Collect atomic observations, connect complementary observations,
test direction and alternatives, choose the least speculative abstraction,
and preserve uncertainty. Feature cooperation does not establish direct
service communication. Sequence does not establish automation. Missing
documentation does not prove absence. Do not invent protocols, microservices,
cloud internals, APIs, queues, data flows, integrations, or outcomes.

Classify every entity and relationship:

- `D`: directly documented.
- `R`: reasoned reconstruction supported by referenced premises. Record the
  derivation and what remains unestablished.
- `H`: plausible hypothesis with materially different alternatives. Do not
  include it as an established diagram relationship.
- `U`: unresolved, conflicting, dated, or insufficient. Preserve the caveat;
  do not silently draw an edge.

Create both exact outputs:

1. `07-final-report/diagram-models.md`, containing an entity registry, a
   relationship registry, inference chains, and separate sections named
   `Model 01`, `Model 02`, `Model 03`, and `Model 04`.
2. `tools/outputs/diagram-models.json`, the machine-readable source of truth
   conforming to `research_control/schemas/diagram-models.schema.json`.

Every D/R entity or relationship must cite existing fact IDs or source IDs.
Every R/H record needs a reasoning note. Use stable IDs across all four
models. Each diagram model must specify its entities, drawable D/R
relationships, question answered, supported takeaway, structure, deliberate
omissions, and caveats. H/U relationships may remain in the shared registry
or discussion but must not appear in a model's `relationship_ids` as
established connections.

The four model records must use these exact IDs, titles, and subtitles:

1. ID: `01-product-capability-map`
   Title: `Capability taxonomy / inventory`
   Subtitle: `What does this company offer, and how are its capabilities organized?`
2. ID: `02-operating-model`
   Title: `Operating model / behavior`
   Subtitle: `How does the product turn an input or need into an outcome?`
3. ID: `03-enterprise-logical-architecture`
   Title: `Enterprise logical architecture / structure`
   Subtitle: `How are the major functional domains organized, and how does the platform relate to its environment?`
4. ID: `04-technical-dependency-map`
   Title: `Focused technical dependencies / receipts`
   Subtitle: `What consequential technical relationship, limitation, or architectural distinction does the research establish?`

Model 01 is a capability taxonomy, not a flow. Model 02 explains supported
behavior or lifecycle. Model 03 explains system boundaries, responsibilities,
and enterprise fit without assuming deployment topology. Model 04 selects one
consequential technical dependency, limitation, prerequisite, supported path,
or architectural distinction not already explained by the other views.

Do not draw anything. The scheduler will not release the build task until the
model registry passes deterministic validation.
