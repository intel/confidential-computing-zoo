## RENAMED Requirements

### Requirement: Background thread lifecycle
FROM: The submit daemon SHALL run as a `threading.Thread(daemon=True)` started during the Trust API's FastAPI lifespan.
TO: The submit daemon SHALL run as a `threading.Thread(daemon=True)` started during TruCon's FastAPI lifespan.

### Requirement: Ordered Rekor submission
FROM: (no name change, only body references)
TO: All references to "Trust API" in requirement text SHALL use "TruCon"

### Requirement: Confirmed record update
FROM: It SHALL also update `chain_state.head_log_id`.
TO: It SHALL also update `chain_state.head_log_id`. (no behavioral change, naming only)
