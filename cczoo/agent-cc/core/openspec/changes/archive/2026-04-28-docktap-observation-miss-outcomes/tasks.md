## 1. Observation Outcome Contract

- [x] 1.1 Extend local response enrichment so selected probe-style operations record `response.outcome` using the first-wave values `ok`, `miss`, and `error`.
- [x] 1.2 Apply benign `miss` handling only to `image_inspect`, `network_inspect`, `volume_inspect`, and `plugin_inspect` daemon `404` responses while keeping proxy/local failures and other non-benign responses classified as `error`.

## 2. Focused Coverage and Documentation

- [x] 2.1 Add focused tests covering successful probe outcomes, benign `404` miss outcomes, and proxy/local failure separation for the selected probe-style observation types.
- [x] 2.2 Update Docktap architecture/API docs to distinguish local `response.outcome` semantics from TruCon `operation_result`, and to document that container detail `inspect` `404` handling remains deferred.