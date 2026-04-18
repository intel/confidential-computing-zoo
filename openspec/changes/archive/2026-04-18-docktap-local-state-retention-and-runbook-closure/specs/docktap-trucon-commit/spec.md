## ADDED Requirements

### Requirement: Docktap retry bookkeeping has bounded post-resolution retention
Docktap SHALL retain retryable local submission records until they are acknowledged by TruCon or marked terminally failed. After resolution, Docktap SHALL retain acknowledged submissions for the configured acknowledged-retry retention window and terminally failed submissions for the configured terminal-retry retention window, then garbage-collect them without affecting the already-completed Docker response.

#### Scenario: Retryable submission is never garbage-collected while pending
- **WHEN** Docktap has a local submission record in retryable state awaiting another TruCon commit attempt
- **THEN** periodic garbage collection SHALL NOT remove that record

#### Scenario: Acknowledged submission expires after short diagnostic window
- **WHEN** Docktap has an acknowledged local submission record and the configured acknowledged-retry retention window has elapsed
- **THEN** Docktap SHALL remove that record during periodic garbage collection

#### Scenario: Terminally failed submission expires after operator window
- **WHEN** Docktap has a terminally failed local submission record and the configured terminal-retry retention window has elapsed
- **THEN** Docktap SHALL remove that record during periodic garbage collection