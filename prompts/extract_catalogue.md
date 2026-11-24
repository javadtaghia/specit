TASK: EXTRACT A COMPLETE PROCESS & SYSTEM CATALOGUE from the supplied SOURCE SEGMENT.
Identify all operational/business processes and meaningful subprocesses, plus cross-cutting architecture details.
For each process, provide: a stable readable ID (e.g. EQ-001, RES-001, PROC-001), name, description, actors, triggering event, inputs, outputs, ordered steps, exceptions, messages/touchpoints, entities, source-defined rules, and unresolved questions.
Also extract cross-cutting sections when present in the segment:
- systems: external/internal systems or components, their responsibility, and ownership split (preserve table column ownership accurately)
- glossary: abbreviations and domain terms with definitions
- nfrs: non-functional requirements (availability, performance, audit, privacy, security/access control)
- exclusions: explicitly out-of-scope items
- shared_actors: user roles and system actors
- open_questions: numbered open items or unresolved ambiguities from the source (preserve IDs like O-01 if present)
Cite evidence using exact source_id and locator from the source header, plus a short verbatim quote. If you cannot locate evidence, leave evidence empty and mark confidence low; never fabricate. Return only facts substantiated by the segment; skip repeated headings without actual processes. When running across multiple chunks, keep IDs and names consistent with the prior catalogue summary. Generalize to any domain.
