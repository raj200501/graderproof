# Preregistrations

Files named `NNNN-<slug>.md`, one per confirmatory study or amendment. Each states hypotheses, metrics, analysis plan, frozen thresholds, sample sizes, the sampling seed, exclusions, stopping rules, and the pilot tasks and seeds that are disjoint from the confirmatory sample.

A preregistration is committed once, when it is frozen, before any data it governs exists, and is never edited afterwards. A needed change is a new, dated amendment file that cites the original, is committed before any data it affects, and is reported as a deviation. `make prereg-verify` and ship-check gate G11 check these rules.
