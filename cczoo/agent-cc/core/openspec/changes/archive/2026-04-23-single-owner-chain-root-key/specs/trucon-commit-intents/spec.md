## MODIFIED Requirements

### Requirement: Commit consumes the reserved intent only after bundle validation
The final TruCon `/commit` path for replayable records SHALL accept `intent_token` together with the signed bundle and SHALL validate that the signed payload matches the reserved `chain_id`, `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` before inserting a queue record or advancing chain state. For chains that declare a single long-term owner key at Event Log 0, the same `/commit` path SHALL also require owner-key authorization for the replayable record before the queue record is inserted.

#### Scenario: Matching bundle and owner authorization consume intent
- **WHEN** `/commit` receives a signed bundle whose signed predecessor fields exactly match the reserved contract for the supplied `intent_token` and the record proves authorization by the chain owner key declared at Event Log 0
- **THEN** TruCon SHALL insert the queue record with the reserved sequence metadata, SHALL update the chain head, SHALL mark the intent `CONSUMED`, and SHALL return the committed `record_id` and `sequence_num`

#### Scenario: Bundle mismatch rejects commit
- **WHEN** `/commit` receives a signed bundle whose predecessor fields differ from the reserved contract for the supplied `intent_token`
- **THEN** TruCon SHALL reject the request, SHALL leave the intent unconsumed or failed according to implementation policy, and SHALL NOT insert a queue record for that attempt

#### Scenario: Missing owner authorization rejects replayable commit
- **WHEN** `/commit` receives a reservation-backed replayable record for a chain that has declared a single owner key at Event Log 0 but the request does not prove authorization by that owner key
- **THEN** TruCon SHALL reject the request, SHALL NOT consume the reserved intent, and SHALL NOT insert a queue record