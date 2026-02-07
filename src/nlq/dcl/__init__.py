"""
DCL (Data Connectivity Layer) — New Capabilities Module.

Two-tier model:
- DCL Core: Metadata only (schemas, mappings, ontology)
- DCL Deep: Reads data values in-flight for entity resolution and conflict detection.
  Never stores. Never persists. Customer opts in explicitly.

Capabilities:
- Entity Resolution (companies/customers v1)
- Golden Records
- Conflict Detection
- Truth Scoring
- Data Quality Feedback Loop
- Temporal Versioning
- Provenance Trace
- Persona-Contextual Definitions
- MCP Server
- Admin Interfaces (Entity Browse, Conflict Dashboard, Manual Resolution)
"""
