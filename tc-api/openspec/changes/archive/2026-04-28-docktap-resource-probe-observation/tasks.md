## 1. Resource Probe Classification

- [x] 1.1 Add explicit read-only classification for selected network, volume, and plugin probe paths.
- [x] 1.2 Preserve existing `image_inspect` and container detail `inspect` behavior while narrowing fallback usage for the new probe families.

## 2. Focused Coverage and Documentation

- [x] 2.1 Add focused tests for representative network, volume, and plugin probe paths, including compatibility checks for existing inspect labels.
- [x] 2.2 Update Docktap architecture/API docs to distinguish the new resource probe labels from lifecycle commit types and to document that benign `404` semantics remain deferred to `GAP-21.4`.