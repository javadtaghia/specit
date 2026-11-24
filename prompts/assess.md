TASK: PERFORM ADVERSARIAL QUALITY REVIEW of the catalogue and generated architecture artifacts.
Return a 0..100 quality score justified by concrete issues (not a subjective grade), critical contradictions or omissions, warnings, coverage gaps, cross-artifact model discrepancies, and actionable recommendations to revise the catalogue or artifacts.
Check:
- Process coverage against the catalogue (flag any processes without generated artifacts as coverage gaps)
- Consistency of actor names, system boundaries, entity names, message/touchpoint names, and state names across artifacts
- Completeness of exception handling, state transition guards, rejected events, idempotency/concurrency rules
- Traceability of source rules, NFRs, exclusions, and open items/questions (ensure none were silently dropped or assumed)
- Deterministic failures provided in the input must be treated as mandatory critical defects
NEVER declare artifacts production approved; the human reviewer controls approval. If something is absent from the source, flag it as unresolved rather than inventing facts.
