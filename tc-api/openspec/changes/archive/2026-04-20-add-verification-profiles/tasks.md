## 1. Profile Contract Foundations

- [x] 1.1 Add shared verification-profile data structures and helper logic for profile verdict states (`verified`, `warning`, `incomplete`, `failed`)
- [x] 1.2 Define shared field extraction and grouping helpers for `build`, `publish`, `launch`, and `docktap-runtime` event sets
- [x] 1.3 Implement launch-attempt grouping by existing `launch_id` and workload-scoped latest-attempt selection rules

## 2. REST Producer Alignment

- [x] 2.1 Update build trusted-log emission to record `output_image_digest`, `dockerfile_digest`, `build_context_digest`, `base_image_digests`, and `build_status`
- [x] 2.2 Update publish trusted-log emission to record `pushed_subject_digest`, `target_ref`, and `publish_status`
- [x] 2.3 Update launch trusted-log emission to record `launch_id`, `workload_id`, `image_digest`, `launch_config_digest`, and launch security projection fields
- [x] 2.4 Update launch trusted-log emission to record resulting instance identities on successful create/start and explicit failure outcomes before instance creation when launch aborts early

## 3. Docktap Runtime Alignment

- [x] 3.1 Update Docktap runtime commits to emit explicit `operation_result` values for submitted lifecycle events
- [x] 3.2 Update Docktap runtime commits to emit profile-required identity fields including `workload_id` and `instance_id` for container-scoped events
- [x] 3.3 Propagate `launch_id` into launch-attributed Docktap `create` and `start` events so launch verification can group REST and runtime evidence under one attempt boundary

## 4. CLI Profile Evaluation

- [x] 4.1 Extend `tc-verify` JSON output to include profile-scoped verdicts and profile-specific findings alongside replay and attested-head results
- [x] 4.2 Extend `tc-verify` text output to render per-profile results without collapsing them into one synthesized workload verdict
- [x] 4.3 Implement profile evaluation rules for `build`, `publish`, `launch`, and `docktap-runtime`, including hard failures, warning-only omissions, and incomplete evidence handling

## 5. Validation And Regression Coverage

- [x] 5.1 Add unit tests for build, publish, launch, and docktap-runtime profile evaluation and verdict derivation
- [x] 5.2 Add tests for latest-launch grouping by `launch_id`, including pre-create launch failure and successful launch with resulting instance identities
- [x] 5.3 Add producer payload-shape tests for REST and Docktap event emission to ensure required audit fields are present