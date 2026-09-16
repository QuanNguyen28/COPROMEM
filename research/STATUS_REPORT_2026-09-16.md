# CoProMem / CoProCon: research status, 16 September 2026

This is a retrospective evidence report, not an experiment registration or permission to resume research. It preserves the original negative results and distinguishes subsequent sensitivity analyses. The current user decisions override historical notes saying that a goal is active or proposing a next cycle. The companion [claim-evidence ledger](CLAIM_EVIDENCE_LEDGER_2026-09-16.md) specifies the limits of each potentially publishable claim.

Scope: existing source, research records, saved reports, manifests, lineage, accounting records and already exposed artifacts; primary-source literature verification. No experimental provider requests, native benchmark actions, tests, lint runs or experiment reruns were made to prepare this report. No reserved test payload was opened for this report. Only this file and its companion are authorized new project files. This is not a fresh exhaustive certification of every source file or every historical access.

## 1. Executive conclusion

The original objective was to improve future agent performance by extracting transferable corrective procedures from near-matched successful and failed trajectories, rather than retaining only raw trajectories or free-form reflections. CoProMem evolved into CoProCon by making the proposed memory executable: scoped conditions and repair/intervention logic, validated at a saved handoff checkpoint. Subsequent work progressively moved the bottleneck from memory representation, to runtime fidelity, to source quality, to repair construction, to activation, and finally back to candidate generation.

**Current verdict: preserve the engineering and negative evidence; stop the current scientific configuration. No reproducible, causally attributable learned-method advantage or publishable superiority has been demonstrated.** The proposed contract-guided causal recovery direction is an untested idea with substantial prior-art overlap, not an approved successor.

| Label | Current conclusion |
|---|---|
| SUPPORTED | Bounded isolated execution, saved-prefix replay, native scoring, public-binding inspection and static checking work on their recorded fixtures and eligible episodes. These are engineering results, not method superiority. |
| PRELIMINARY | Specific procedural edits improve saved native continuations on two inspected build scenarios. Post-hoc Cycle 24B finds two additional teacher repairs on four different inspected build tasks. These establish local repair opportunities, not transferable learning. |
| FALSIFIED | Strict positive quality superiority of a new activation selector over the fixed manual risk-reduction policy is impossible on the eleven available fixed pairs: manual selection already equals their per-pair quality oracle, 8/11. This is a finite-sample ceiling, not a universal impossibility theorem about learned activation. |
| INCONCLUSIVE | Learned contracts beyond competent static/manual controls; generalization, safety, efficiency, automatic induction and multi-agent attribution. There is no valid positive comparison establishing these claims. |
| NOT TESTED | The paused Cycle 23 learned-proposal experiment, the rejected genuinely unseen candidate-generation pilot, and the proposed B+C contract-guided causal recovery formulation. |
| KILLED CONFIGURATION | The current AppWorld held-out-pilot configuration and its reserved allocations as a claimed untouched test resource. Affirmative untouched custody and a complete conservative budget were not established. The user has accepted KILL as final. |

Other non-negotiable conclusions:

- Strict Cycle 24 remains **0/4 accepted proposals**. Cycle 24B is a **separate post-hoc format-only sensitivity**, with 4/4 parseable proposals and 2/4 native task improvements. It does not replace the strict result.
- No stateful learned contract bank has been shown to outperform the fixed static/manual controls. Missing learned-arm predictions are not a measured tie, but they cannot support a learning claim.
- A manually authored, domain-specific synthetic contract can work without establishing automatic discovery or general-purpose memory.
- The strongest defensible output today is an auditable negative/diagnostic case study: state and interface errors can mimic learning failures; repair opportunities do not establish activation value; a strong manual control can exhaust a small sample's quality headroom.
- Recommended decision: **terminate this AppWorld configuration; retain reusable artifacts; keep all research execution paused.** Consider a new formulation only after user review and a precise novelty difference that survives the literature in Section 10. Sunk implementation effort is not a reason to continue.

## 2. Evolution of the idea

The initial textual-memory objective is documented in the supplied research conversation and reflected in the preserved [CoProCon research document](../docs/CoProCon_research_doc.md), [initial audit](000_initial_state.md), [pivot specification](008_PIVOT_RESEARCH_SPECIFICATION.md) and [code-grounded research description](009_CURRENT_CODE_RESEARCH_DOCUMENT.md). These documents were written at different stages; they are not a single unchanged preregistration. The original external proposal was not independently re-certified against every subsequent implementation in this reporting task.

| Transition | Reason and motivating evidence | Evidence against the stronger claim | What remains useful |
|---|---|---|---|
| Textual corrective procedural memory | Store compact lessons rather than full trajectories; transfer recurring procedures between episodes. | Synthetic roles/rules and separate-call GSM8K comparisons do not identify a memory effect. ExpeL and other textual-memory methods already occupy much of this space. | Explicit memory provenance, episode traces, no-memory/success-only controls. |
| Contrastive success/failure memory | Use near-matches to identify what changed between success and failure. | Cycles 2–3 admitted no contracts; outcome differences often did not correspond to differences in the planner artifact. ExpeL, AutoGuide and CONTRAMEM undermine a generic contrast novelty claim. | Pair lineage and the distinction between outcome contrast and actionable procedural contrast. |
| Executable procedural contracts / CoProCon | Replace advice with scoped, inspectable predicates and interventions; test an edit at a fixed checkpoint. | The original successful synthetic rules were domain-authored. Later native effects did not become an admitted, transferring learned contract. ICE/Horn-ICE, AgentSpec and contract systems are strong prior art. | Typed artifacts, explicit intervention boundaries, validation hooks, immutable source records. |
| Static verification and targeted repair | Native source failures and crossovers exposed undefined names, missing inputs and incomplete collection production. | Binding-aware F821 solves the observed missing-name class. Binding/pagination repair is not uniquely learned; some fixes are ordinary interface correction. | Public-presence probe, competent static control, local whole-program/block repair evidence. |
| Learned activation | Learn when a fixed candidate should replace the original continuation. | Cycle 19's code-only representation cannot separate some outcomes; manual risk reduction later reaches the available quality oracle on eleven pairs. No selector should be fitted again on those pairs. | Fixed-candidate causal decomposition and an explicit ceiling test. |
| Repair-candidate generation | Once activation has no remaining quality headroom, useful candidates for remaining failures become the proposed bottleneck. | Cycle 24 is strictly 0/4; 24B's two repairs use a stronger teacher and task-specific failure history, without matched generation controls. The proposed new pilot fails custody/budget prerequisites. | Saved raw proposals and a clean separation between parsing, gate acceptance and native repair outcome. |
| Proposed contract-guided causal recovery, B+C | Combine executable handoff obligations with localization and responsible-agent recovery. | No implemented or tested algorithm; DoVer, CausalFlow, CAR, AgentTether, SymTrace/SymFail and AUDITA substantially cover the component combination. | A question for conceptual review only, not a demonstrated contribution or approved experiment. |

The shift from ARCO-style within-episode routing to across-episode procedural knowledge was an intended boundary, not an experimentally demonstrated benefit. Changing models, team structure, memory and repair policy simultaneously would destroy attribution. The present results do not establish a general multi-agent memory mechanism.

## 3. Complete experiment and diagnostic timeline

### Reading the tables

Dates below are record/run-label dates. Historical GSM8K filenames are dated 2026-09-15; numbered-cycle reports are dated 2026-09-16, including records whose UTC timestamp falls late on 15 September. Exact timestamps remain in the artifacts. A scenario/task is the independent cluster; seeds, repetitions, checkpoints, variants and replay branches are not additional independent tasks.

`G/H` denotes beneficial/harmful native success flips relative to the stated control unless explicitly labeled checker classification. A native execution is not a provider call; internal AppWorld API operations are a third, separate count. `USD 0 new API` never means local work was free. KEEP in an old record means retaining the particular component or evidence, not passing the overall scientific gate. Table costs are reconciled in Section 9.

### 3.1 Historical synthetic and real-task experiments

| Record/date; question and change | Data and independent units | Model; calls; reported USD | Result, G/H and validity | Decision and evidence |
|---|---|---|---|---|
| Synthetic/tiny, legacy and 16 Sep regression: can procedural guards prevent designed join/count errors? Domain-authored templates, simulated agents/costs. | Tiny: 6 tasks, 2 authored template clusters. Full: 32 tasks, 8 template clusters. | No experimental LLM; simulated cost units, not USD. | Tiny CoPro 6/6, no memory 3/6, success-only 4/6; G3/H0 vs no memory. Full CoPro/static 26/32, no memory 13/32, textual 22/32, sham 17/32. Executor-swap CoPro 22/32 vs no memory 11/32 is still synthetic. | KEEP regression; REVISE efficacy interpretation. [Regression artifacts](../artifacts/research/local_regression_20260916), [contracts](../src/copromem/contracts.py), [synthesis](../src/copromem/synthesis.py), [initial audit](000_initial_state.md). |
| GSM8K micro, 15 Sep: real model execution of the three-arm prototype. | 3 build, 4 test tasks. | Ministral 3B/OpenRouter; 33 calls; 0.00145844. | No memory 3/4, success-only 2/4, CoPro 1/4; G0/H2 vs no memory. Independent upstream calls confound memory. | REVISE. [Raw report](../artifacts/gsm8k_real_micro_20260915.json). |
| GSM8K micro DeepSeek, 15 Sep: backend change. | 3 build, 4 test tasks. | DeepSeek V4 Flash/OpenRouter; 30; 0.002542785072. | 2/4, 3/4, 2/4; G1/H1; contract bank empty. | REVISE. [Report](../artifacts/gsm8k_real_micro_deepseek_v4_flash_20260915.json). |
| GSM8K 10-test, 15 Sep: larger stress slice. | 3 build, 10 test tasks. | DeepSeek V4 Flash/OpenRouter; 68; 0.005705774462. | 8/10, 7/10, 9/10; G2/H1. A one-run apparent gain is not attributable. | REVISE. [Report](../artifacts/gsm8k_real_10test_deepseek_v4_flash_20260915.json). |
| GSM8K seed17, 15 Sep: repeat. | Same 10-task slice, not 10 new tasks. | Same model/route; 66; 0.005771227818. | 7/10, 8/10, 7/10; G0/H0. | REVISE. [Report](../artifacts/gsm8k_real_10test_deepseek_v4_flash_seed17_20260915.json). |
| GSM8K seed17 cumulative, 15 Sep: memory update variation. | Same slice. | Same; 66; 0.003297551260. | 7/10, 6/10, 7/10; G0/H0. | REVISE. [Report](../artifacts/gsm8k_real_10test_deepseek_v4_flash_seed17_cumulative_20260915.json). |
| GSM8K seed23 cumulative, 15 Sep. | Same slice. | Same; 68; 0.003263101494. | 7/10, 7/10, 7/10; G1/H1. | REVISE. [Report](../artifacts/gsm8k_real_10test_deepseek_v4_flash_seed23_cumulative_20260915.json). |
| GSM8K seed41 cumulative, 15 Sep. | Same slice. | Same; 67; 0.003055599262. | 7/10, 8/10, 8/10; G1/H0. | REVISE. [Report](../artifacts/gsm8k_real_10test_deepseek_v4_flash_seed41_cumulative_20260915.json). |
| GSM8K seed73 cumulative, 15 Sep. | Same slice. | Same; 67; 0.003018158474. | 7/10, 8/10, 8/10; G1/H0. | REVISE. [Report](../artifacts/gsm8k_real_10test_deepseek_v4_flash_seed73_cumulative_20260915.json). |
| GSM8K literature adaptation, seed42, 15 Sep. | 10 build, 20 test tasks; not paired common planner artifacts. | DeepSeek V4 Flash/OpenRouter; 210; 0.013183364132. | AWM 17/20, CoPro 16/20, CRITIC originally 8/20 then 17/20 after post-hoc null-correction carry-forward; ExpeL 14/20 invalid because literal `None` entered memory. | REVISE; exclude invalid ExpeL comparison. [Original](../artifacts/gsm8k_literature_seed42_20test_20260915.json), [separate reconciliation](../artifacts/gsm8k_literature_seed42_20test_20260915_reconciled.json). |

Ordering in the three-arm rows is no memory / success-only / CoPro. The 675 reported calls and nine historical costs are counted once; checkpoint and reconciled copies are not new experiments. G/H from separately generated plans are observed arm differences, not clean intervention effects. Provider seed labels do not certify deterministic sampling.

### 3.2 Cycles 1–15: representations, source quality and local repair

| Cycle, 16 Sep; hypothesis/change | Data; genuinely independent units | Model/provider; new calls; settled USD | Principal result, limitations and decision | Evidence |
|---|---|---|---|---|
| 1: freeze planner checkpoints and compare six continuations. | 3 build + 4 development tasks; 2 repeats = 8 evaluation rows, 4 independent evaluation tasks. | Ministral 3B / Mistral via OpenRouter; 54 physical calls, 70 logical requests, 16 cache hits; 0.00152572. | No-memory, success-only, textual and historical empty-bank CoPro all 8/8; static and sham each 7/8. Static G0/H1 and sham G0/H1 on different rows. KEEP paired protocol; no learning win. | [Decision](001_cycle_decision.md), [store](../artifacts/research/cycle01_paired). |
| 2: admit contracts from repeated same-task success/failure contrast. | 12 GSM8K train tasks, 3 repeats = 36 episodes. | Ministral 3B / Mistral; 72; 0.00209930. | 35 successes, 1 failure; 2 contrast pairs but one independent task, below two-task admission requirement. 0 candidates, 0 bank; no downstream evaluation. REVISE. | [Protocol](002_induction_preregistration.md), [result](003_cycle02_decision_and_cycle03_preregistration.md), [store](../artifacts/research/cycle02_induction). |
| 3: weaker backend to create more informative failures. | Same 12 tasks, 36 episodes. | Gemma 3 4B / DeepInfra BF16; 72 completed, 74 attempts; 0.00153115 settled. | 25 successes, 11 failures; 10 pairs over 5 tasks, but all paired structural signatures identical and 6 full planner artifacts identical. 0 candidates/bank. Unit ambiguity and truncation further weaken labels. PIVOT from this representation. | [Result](004_cycle03_decision.md), [store](../artifacts/research/cycle03_induction). |
| 4: offline intervention audit of Cycle 1. | All 8 saved rows, 4 tasks; no new sample. | None; 0 calls; 0 new API USD. | Each static/sham arm activates 4 times, all from successful originals; G0/H1 each. Historical logical intervention costs 0.00017380 / 0.00016118 are not new bills. REVISE. | [Protocol](005_cycle04_offline_preregistration.md), [result](006_cycle04_decision_and_adapter_preflight.md), [store](../artifacts/research/cycle04_offline). |
| 5: can isolated AppWorld replay and unchanged scoring work safely? | Six configured fixture cases centered on one authored diagnostic task, not six research scenarios. | None; 0 calls; 0 new API USD. | Empty, mutating, Unicode and exception/recovery pairs match; native failures remain despite completion flags. Forbidden action blocked; 15-second timeout retained. Privileged 5/5 oracle is excluded. KEEP bounded runtime. | [Requirements](011_REQUIREMENTS_AND_NEXT_CYCLE.md), [result](012_CYCLE05_SANDBOX_AND_NATIVE_SCORER.md), [store](../artifacts/research/cycle05_stateful). |
| 6 runtime: preserve typed bindings/functions/random/error behavior. | One authored fixture task. | None; 0 calls; 0 new API USD. | Tested live/replay behavior matches; this precedes source collection and is not source success. KEEP. | [Record](013_CYCLE06_SOURCE_PREREGISTRATION.md), [store](../artifacts/research/cycle06_runtime). |
| 6 source: collect naturally mixed outcomes with the first stateful policy. | Four build scenarios, two repetitions = 8 episodes. | Ministral 3B / Mistral; 240; 0.06122978. | 0/8 native success, 0/4 mixed scenarios; 8/8 replay eligible. 113/120 action errors, 91 AST errors, 114 executor fallbacks. REVISE source interface. | [Public interface audit](014_APPWORLD_PUBLIC_INTERFACE_AUDIT.md), [result](015_CYCLE06_SOURCE_RESULTS.md), [store](../artifacts/research/cycle06_appworld_source). |
| 7: public onboarding v2 and raw-Python output. | Same four scenarios / 8 episodes. | Ministral 3B / Mistral; 240; 0.05485080. | 0/8 success; 8/8 replay eligible; 56 action errors, 2 AST errors, 57 format fallbacks. Better format is not native efficacy. REVISE. | [Protocol](016_CYCLE07_ONBOARDING_PREREGISTRATION.md), [result](017_CYCLE07_RESULTS_AND_BACKEND_PREREGISTRATION.md), [store](../artifacts/research/cycle07_appworld_source). |
| 8: stronger general backend under the revised interface. | Same four scenarios / 8 episodes. | Qwen3 30B A3B Instruct 2507 / Nebius FP8; 240; 0.09919890. | 0/8 success; 8/8 replay eligible; 35 action errors, no AST errors. REVISE. | [Result](018_CYCLE08_RESULTS_AND_CODER_PREREGISTRATION.md), [store](../artifacts/research/cycle08_appworld_source). |
| 9: coding model. | Same four scenarios / 8 episodes, 117 actions. | Qwen3 Coder / DeepInfra Turbo; 234; 0.19375710. | 0/8 success; 7 eligible, one unsupported infinity state. 20 action errors; 101/117 context entries truncated. REVISE. The failed eligibility record was not retrospectively promoted. | [Result](020_CYCLE09_RESULTS_AND_RUNTIME_GATE.md), [store](../artifacts/research/cycle09_appworld_source). |
| 10: typed infinity and longer replay runtime gate. | Two bounded regression cases, including a 25-action fixture and previously unsupported prefix; no efficacy sample. | None; 0 calls; 0 new API USD. | Runtime cases pass; 50-action capacity separately unit-tested. KEEP infrastructure; preserve old Cycle 9 failure. | [Record](020_CYCLE09_RESULTS_AND_RUNTIME_GATE.md), [store](../artifacts/research/cycle10_runtime_gate). |
| 11: 50-step horizon, 64K context, 16K output caps. | Original four scenarios / 8 episodes, 167 actions. | Qwen3 Coder / DeepInfra Turbo; 334; 0.44051750. | 1/8 success, one mixed scenario `aa8502b`; 8 replay eligible. Seven completion flags but only one native success; 46 action errors. KEEP source for one diagnostic; not adequate population evidence. Raw result says REVISE while narrative retains a narrow KEEP. | [Protocol](021_CYCLE11_CONTEXT_HORIZON_PREREGISTRATION.md), [result](022_CYCLE11_RESULTS_AND_CROSSOVER_PREREGISTRATION.md), [store](../artifacts/research/cycle11_appworld_source). |
| 12: same-program crossovers at frozen origins. | One scenario, two origins × two final programs × two repeats = 8 native executions and 8 scorer runs. | None; 0 calls; 0 new API USD. | Whole successful program repairs failed origin; failing program harms successful origin: G1/H1. Successful program uses 23 native API operations vs 7, +16. KEEP local repair opportunity, not a learned selector result. | [Record](022_CYCLE11_RESULTS_AND_CROSSOVER_PREREGISTRATION.md), [store](../artifacts/research/cycle12_action_crossover). |
| 13: backward producer-block transplant and deletion tests. | Same scenario, 2 origins, 5 variants, 10 cells × 2 repeats = 20 native/scorer runs. | None; 0 calls; 0 new API USD. | One retained four-statement pagination-related block gives G1/H0 across origins. No tested deletion retained the intended effect; deletion variants include harmful flips on the successful origin. Not global minimality or learned scope. KEEP local edit. | [Protocol](023_CYCLE13_PROCEDURAL_DIFF_PREREGISTRATION.md), [result](025_CYCLE13_RESULTS_AND_RESEARCH_STATUS.md), [store](../artifacts/research/cycle13_procedural_diff). |
| 14: seek independent mixed source scenarios. | Four additional build scenarios / 8 episodes. | Qwen3 Coder / DeepInfra Turbo; 434; 0.92504400. | 4 successes, but two all-success scenarios; 7 replay eligible, one unsupported `Match`. No new mixed scenario or proposal. REVISE source strategy. | [Protocol](026_CYCLE14_INDEPENDENT_SOURCE_PREREGISTRATION.md), [result](027_CYCLE14_RESULTS_AND_NEXT_SOURCE_DECISION.md), [store](../artifacts/research/cycle14_appworld_source). |
| 15: reflection-assisted recollection. | Eight already used scenarios, one new retry each; no new scenario allocation. | Qwen3 Coder / DeepInfra Turbo; 8 critic + 536 agent = 544 calls; 1.07711820. | 3/8 successes, all replay eligible; no new mixed scenario among seven remaining opportunities. One F→T is on already mixed `aa8502b`, without a matched no-reflection retry. One old proposal, no new proposal. REVISE. | [Protocol](028_CYCLE15_REFLECTION_SOURCE_PREREGISTRATION.md), [result](030_CYCLE15_RESULTS_AND_SOURCE_REVISION.md), [store](../artifacts/research/cycle15_reflection_source). |

All source-collection changes above change model/interface/horizon or recollection conditions. Their before/after success rates are diagnostic, not controlled estimates of a memory mechanism. No native repair G/H is defined for source collection alone.

### 3.3 Cycles 16–24B and the strict decision gate

| Cycle, 16 Sep; hypothesis/change | Data / independent units / execution | Result, flips and limits | Decision and evidence |
|---|---|---|---|
| 16A: extend runtime for a long official source. | Two runtime cases, including a 100-action counter and old successful prefix; 4 native/scorer executions; no model calls. | Initial Docker allowlist build failure preserved; final bounded repeats pass. Not new policy success. | KEEP runtime. [Gate](035_CYCLE16_LONG_SOURCE_RUNTIME_GATE.md), [result](036_CYCLE16A_RESULT_AND_OFFICIAL_REPLAY_PREREGISTRATION.md), [store](../artifacts/research/cycle16_runtime_gate). |
| 16B: replay official public source code locally. | Eight already-build scenarios; 8 archive programs, 16 native/scorer runs. Original GPT-4o acquisition cost unknown; 0 new provider calls. | 4 successes / 4 failures, all replay eligible; one new mixed scenario `b7a9ee9`. Every local output differs from historical output; this is unchanged-code local execution, not original policy reproduction. Six contrasts in 32-source corpus still produce only the old final-action proposal. | KEEP exploratory source; REVISE alignment. [Result](037_CYCLE16_RESULTS_AND_ALIGNMENT_LIMIT.md), [store](../artifacts/research/cycle16_official_source_replay). |
| 17A: screen every eligible boundary rather than final actions. | Six contrasts; 1,323 action pairs; 2 scenarios supply proposal-bearing records. Zero native/provider calls. | 1,188 null, 63 unsupported, 42 error-donor, 30 proposal-bearing pairs; 34 records / 26 distinct interventions. These counts are not 26 independent tasks or repairs. | KEEP coverage diagnostic. [Protocol](038_CYCLE17_ALL_BOUNDARY_SCREEN_PREREGISTRATION.md), [result](039_CYCLE17A_RESULT_AND_EFFECT_PREREGISTRATION.md), [store](../artifacts/research/cycle17_all_boundary_screen). |
| 17B: test those boundary edits. | 26 edits + 4 controls = 30 cells; 60 native/scorer runs; 2 scenarios; no provider calls. | Four successful edits all come from old `aa8502b` actions 10–13, each +16 native API operations. All six new-scenario edits fail; 14 edited cells hit `NameError`. All originals fail, so harm on successful originals is unmeasured. | REVISE input closure. [Result](041_CYCLE17_EFFECT_RESULT_AND_BINDING_FAILURE.md), [store](../artifacts/research/cycle17_boundary_effects). |
| 18A: bind donor inputs using public API keyword structure. | 34 prior records: 5 changed, 8 unchanged, 21 rejected; no native/provider calls. | Rejections: 20 missing input closure, 1 output closure. Five changed proposals all on `b7a9ee9`. | KEEP construction diagnostic. [Protocol](042_CYCLE18_PUBLIC_BINDING_PREREGISTRATION.md), [result](043_CYCLE18A_RESULT_AND_BOUND_EFFECT_PREREGISTRATION.md), [store](../artifacts/research/cycle18_public_binding). |
| 18B: native effects of bound repairs. | Five edits + three controls, 16 native/scorer runs; one newly repaired scenario, not five; no provider calls. | One G, four unchanged failures; `c18b-edit-02` reaches 4/4 checks at action 19. Native API 151→185, +34; 298.940 recorded seconds. No successful-origin safety test. | KEEP second local repair; no shared contract. [Result](044_CYCLE18_BOUND_REPAIR_RESULT.md), [store](../artifacts/research/cycle18_bound_effects). |
| 19: can AST-count predicates identify repair value? | Two effect-backed pairs / four code examples; 454 candidate clauses; 48 correlated saved effect/control records (8 pass, 40 fail), 2 scenarios. Zero new executions/calls. | 18 training-consistent clauses; none consistent across all records. Identical AST representation can accompany opposite contextual outcomes. This falsifies adequacy of that code-only representation, not all contextual learning. | REVISE representation. [Protocol](045_CYCLE19_CODE_PREDICATE_IDENTIFIABILITY_PROTOCOL.md), [result](046_CYCLE19_PREDICATE_RESULT_AND_CONTEXT_LIMIT.md), [store](../artifacts/research/cycle19_code_predicates). |
| 20: richer public boundary observation. | Six planned cells / 12 native runs were NOT executed. No provider calls. | Proposed namespace/type envelope conflicts with unchanged safety guard on `globals`, `locals`, `type`; blocked in preflight. No native noninterference result for this design. | REVISE to presence-only. [Protocol](047_CYCLE20_PUBLIC_BOUNDARY_OBSERVATION_GATE.md), [result](048_CYCLE20_PREFLIGHT_RESULT_AND_PRESENCE_REVISION.md), [store](../artifacts/research/cycle20_observation_preflight). |
| 21: public variable-presence probe without values. | Three known checkpoints in 2 scenarios; 6 cells / 12 native/scorer runs; 32 queried names, not 32 tasks. No provider calls. | All three tested probe/original pairs preserve continuation outcome; no extra native API operation, but an extra code-action probe. 220.788 recorded seconds. | KEEP bounded observation interface. [Result](049_CYCLE21_PUBLIC_PRESENCE_RESULT.md), [store](../artifacts/research/cycle21_public_presence). |
| 22: isolated F821 static A versus binding-aware static B. | 14 frozen records, 3 checkpoints, 2 scenarios; 28 original + 28 repeated checker processes + 4 preflight processes. Zero model and new native calls. | A: TP5/FP1/TN8/FN0. B: TP5/FP0/TN9/FN0. One checker-classification G, zero H; native task flips not measured. Four B-clear records still fail task. | KEEP B; overall REVISE, not GO. [Protocol](050_CYCLE22_LOCAL_ERROR_AND_STATIC_CONTEXT_PROTOCOL.md), [result](051_CYCLE22_STATIC_CONTEXT_RESULT.md), [strict decision](056_CYCLE22_STRICT_DECISION_REPORT.md), [store](../artifacts/research/cycle22_static_name_check). |
| 23 preparation: learned monitor proposals and isolated sandbox. | 14 known records; 12 requests specified (two folds × contrast/success-only × three seed labels), not submitted. Ten authored runtime fixtures run twice, 20 sandbox processes / 14.327 seconds. | Runtime bounded preflight works; string normalization destroys relevant semantic distinctions. No learned proposal run, native comparison or model cost. Sandbox location remains Cycle 23; not relabeled as Cycle 22. | REVISE / PAUSE. [Protocol](053_CYCLE23_MONITOR_PROPOSAL_PROTOCOL.md), [inputs](054_CYCLE23_INPUT_PREFLIGHT_STATUS.md), [sandbox](055_CYCLE23_SANDBOX_AND_INTERFACE_FREEZE.md), [store](../artifacts/research/cycle23_monitor_sandbox_preflight). |
| 24 precollection correction: validate frozen teacher metadata. | Four already inspected build failures; local focused check, no provider calls in v1 store. | `ast_identity` text had been treated as a hash. Focused test failed but PowerShell continued preparation; v2 corrected metadata in a separate store. Original failure remains. | REVISE preparation, not an efficacy pass. [Correction](063_CYCLE24_PRECOLLECTION_METADATA_CORRECTION.md), [original store](../artifacts/research/cycle24_teacher_repair_source). |
| 24 strict: one stronger-teacher repair per saved failure. | Four build scenarios / one failed checkpoint each. Claude Sonnet 4.6 / Anthropic via OpenRouter; 4 calls; 134,674 input + 2,846 output tokens; USD 0.44671200. | All four raw replies violate strict JSON-only format: **0/4 accepted**, 4 format-invalid. No strict native effect run. Teacher sees task-specific public history and binary failure feedback; no held-out contrast treatment. | REVISE strict source protocol; preserve original result. [Protocol](062_CYCLE24_ONE_SHOT_TEACHER_REPAIR_PROTOCOL.md), [strict record](064_CYCLE24_STRICT_RESULT_AND_FORMAT_COMPATIBILITY.md), [v2 store](../artifacts/research/cycle24_teacher_repair_source_v2). |
| 24B: post-hoc format-only sensitivity. | Same four raw replies; unique JSON substring extraction, no changed teacher content, no new provider calls. Four proposals / 16 native and 16 scorer executions. | 4/4 format-valid, 0 null/unsafe proposals; 2 beneficial flips, 0 observed harmful flips, 2 native failures retained. All originals failed, so harmful flips on initially successful tasks were impossible to observe. | KEEP local sensitivity only; REVISE scientific attribution. [Separate completed effect report](../artifacts/research/cycle24b_teacher_format_compat/effect_reports/37a9059aac761ae82e8ee2c59af4acd2443bf812b741ea4015b8538a99f44df0.json), [store](../artifacts/research/cycle24b_teacher_format_compat). |

Unless explicitly priced above, rows in this table incurred USD 0 **new provider cost**, with local/container/native compute unpriced. Archived teacher/source costs are not charged again when outputs are reused.

### 3.4 Important unnumbered diagnostics and decisions

| Record/date | Question, data, result and limitations | Decision / evidence |
|---|---|---|
| Initial source/integrity audit, 16 Sep | Found synthetic hardcoding, separate-call confounding, an invalid ExpeL memory, incomplete vendor checkouts and accounting/test gaps. No new model or benchmark result. | REVISE interpretation. [Initial state](000_initial_state.md), [current-code document](009_CURRENT_CODE_RESEARCH_DOCUMENT.md), [integrity records](../artifacts/research/integrity_20260916). |
| Windows/Linux AppWorld preflights, 16 Sep | Windows `SIGALRM`/logger issues; database restoration alone did not reset Python counter state (1→2). Clock/freezer cleanup failures preserved. An authored wrong clock expression was corrected; matching an error was not counted as a pass. Fresh-prefix reconstruction succeeded only on bounded later checks. | REVISE naïve resume; KEEP isolated-prefix approach. [Windows failure](007_appworld_windows_preflight_failure.md), [resume audit](010_NATIVE_ADAPTER_AND_RESUME_AUDIT.md), [preflight artifacts](../artifacts/research/appworld_preflight_20260916). |
| Baseline provenance/component gates, 16 Sep | ExpeL installation/import failures followed by compatible-environment CLI, parser and retrieval checks; AWM scorer fixture; ALFWorld authored reset/action/reward check; ReasoningBank lifecycle fixtures; AgentSpec parser/enforcement probes. No paid policy experiment or full published reproduction. | KEEP components, not scores. [Baseline status](BENCHMARK_BASELINE_SHORTLIST.md), [ExpeL](019_EXPEL_NATIVE_REPRODUCTION_PROGRESS.md), [ALFWorld](024_EXPEL_ALFWORLD_NATIVE_GATE.md), [ReasoningBank](029_REASONINGBANK_OFFICIAL_SOURCE_AUDIT.md), [AgentSpec](040_AGENTSPEC_PINNED_PARSER_AND_ENFORCEMENT_AUDIT.md). |
| Backend availability screen / safety checks, 16 Sep | Saved metadata/preflight and safety records informed routes and isolation. They are not task efficacy samples; no separate settled paid-experiment store beyond Section 9 was found. | KEEP operational records; no performance inference. [Backend records](../artifacts/research/backend_screen_20260916), [safety records](../artifacts/research/safety_audits). |
| Cycle 15 concurrent audit incident, 16 Sep | Concurrent materializing audits collided. Incident output preserved; serial rerun passed. A later pass does not erase the failure or make concurrent operation safe. | REVISE execution discipline. [Incident narrative](030_CYCLE15_RESULTS_AND_SOURCE_REVISION.md). |
| Official archive inventory/extraction, 16 Sep | v0.1.0 archive: 139,370 entries, test-only, no allowed train source. v0.1.3: 150,212 entries; nested-metadata parser initially found zero, then corrected. Extracted 32 public logs/version files on 8 already-used scenarios, 255,486 bytes / 164 actions. Database/evaluator bodies excluded. Human worked Spotify demo and missing original request metadata weaken automatic-induction provenance. | KEEP exploratory source only. [Inventory gate](031_OFFICIAL_TRAIN_ARCHIVE_INVENTORY_GATE.md), [v0.1.0 result](032_ARCHIVE_V010_RESULT_AND_V013_INVENTORY_GATE.md), [inventory correction](033_TRAIN_ARCHIVE_INVENTORY_RESULT_AND_PUBLIC_FILE_GATE.md), [extraction](034_OFFICIAL_PUBLIC_SOURCE_EXTRACTION_RESULT.md). |
| Post-C22 semantic collision, 16 Sep | `classical` versus another literal and first-artist/multi-artist counterexamples expose information lost by normalization and by presence-only features. Constructed known-data examples; no native causal test. Zero provider calls. | REVISE observation claim. [Specification](057_MANUAL_CONTROL_SPEC_AND_SEMANTIC_INFORMATION_LIMIT.md), [semantic store](../artifacts/research/post22_public_semantic_view). |
| Post-C22 manual inspector, 16 Sep | Human-authored post-hoc static B plus pagination risk flags all 9 failed records and no successful record; fuller first-artist risk logic additionally flags 1 success. Fourteen correlated records / 2 scenarios; 29 inspections. These are warning classifications, not recovery outcomes. | KEEP strong control; no learned advantage. [Diagnostic](058_POST_GATE_MANUAL_CONTROL_DIAGNOSTIC.md), [result](059_MANUAL_CONTROL_RESULT_AND_LEARNING_GAP.md), [store](../artifacts/research/post22_manual_coverage_control). |
| Saved-branch selector diagnostic, 16 Sep | Eleven fixed original/edit pairs, 3 checkpoints, 2 scenarios. Manual risk reduction chooses 8 successes / 11, G3/H0, equal to outcome-privileged quality oracle. Always-edit yields 4/11, G3/H4. No new native/provider calls. | Final REVISE for activation; no further fitting on these pairs. [Diagnostic](060_SAVED_BRANCH_SELECTION_DIAGNOSTIC.md), [result](061_SAVED_BRANCH_SELECTION_RESULT.md), [store](../artifacts/research/post22_saved_branch_selection). |
| Revised candidate-generation pilot / bounded inventory, conversation decisions | Required no-record and information-matched unpaired controls, clean primary induction, mechanical checkpoints, four independent scenarios and two correlated checkpoints each, exact budget. Not executed. Existing records could not affirm untouched custody or a complete conservative budget. | KILL current AppWorld configuration, explicitly accepted by user. Conversation decisions are not a new frozen experiment artifact. Section 6 preserves their consequences. |
| Strategic A/B/C/B+C pivot discussion, conversation decisions | Fresh one-action repair; invariant induction; localization/credit; combination. No B+C source bank, implementation, registration or results were approved. | REVISE conceptual question only; current task is reporting, not continuation. Section 10 audits the overlap. |

### 3.5 What happened after the Cycle 22 gate?

The registered component comparison passed narrowly: retain binding-aware static B. The learned-method decision was **REVISE, not GO**. Cycle 23 preparation had already started before the stricter instruction; [the decision report](056_CYCLE22_STRICT_DECISION_REPORT.md) explicitly paused its paid proposal run. Later manual diagnostics tested whether static procedural logic exhausted the remaining opportunities. They found the fixed-pair quality ceiling. The proposed bottleneck then moved to candidate generation, motivating the four-teacher-response diagnostic and its separately permitted format sensitivity.

This is a chronology and rationale, **not evidence that the scientific gate cleared**. Successive component KEEP decisions and older statements that an autonomous goal remained active prolonged work without demonstrating learned value. The repository does not by itself establish every intermediate user-approval boundary; missing authorization provenance must not be invented. The user's explicit instruction to finish 24B did not authorize Cycle 25. The final REVISE/KILL decisions and the current pause are controlling.

## 4. Results that actually worked

### 4.1 Engineering, replay and noninterference

The useful implementation is a bounded research harness: source/response capture; content-addressed protocol and result records; isolated AppWorld workers; replaying a saved action prefix into fresh state; running original and edited continuations; unchanged native scoring; static/manual inspection; and append-only request accounting. The retained native source episodes include both successes and failures, rather than treating a model's completion flag as ground truth.

The guarantees are conditional. Supported-state live/replay pairs and repeat checks matched; unsupported infinity and `Match` cases were explicitly excluded at collection time. Database equality alone was shown insufficient. Replay is reconstruction from recorded actions in the pinned environment, not an arbitrary complete VM snapshot or universal deterministic AppWorld promise. Saved downstream actions implement an **open-loop continuation**, not live agent adaptation after intervention. Hash equality identifies stored bytes/configurations, not untouched custody or the counterfactual correctness of a different policy.

The sandbox tests and Cycle 21 establish bounded permission/noninterference properties on authored fixtures and three known checkpoints. They do not certify all code as safe, remove semantic side effects, or establish a general zero-harm theorem. See [runtime record](012_CYCLE05_SANDBOX_AND_NATIVE_SCORER.md), [runtime expansion](020_CYCLE09_RESULTS_AND_RUNTIME_GATE.md), [presence test](049_CYCLE21_PUBLIC_PRESENCE_RESULT.md) and [isolated proposal sandbox](055_CYCLE23_SANDBOX_AND_INTERFACE_FREEZE.md).

### 4.2 What static checking already solves

Cycle 22's frozen evidence is reproduced here to avoid substituting task scores for checker accuracy. `Clear` means only no F821 warning. Task outcomes were saved earlier; no recovery was executed by this checker experiment.

| Frozen row | Abbreviated source | Actual missing name | Static A | Binding-aware B | Saved task outcome |
|---:|---|---|---|---|---|
| 0 | C13 producer-removed, failed origin | None | Clear | Clear | Fail |
| 1 | Same variant, successful origin | None | Clear | Clear | Fail |
| 2 | C13 variant, failed origin | `page_limit` | Warn | Warn | Fail |
| 3 | Same variant, successful origin | `page_limit` | Warn | Warn | Fail |
| 4 | C13 variant, failed origin | None | Warn: `liked_songs` | Clear | Pass |
| 5 | Same variant, successful origin | `liked_songs` | Warn | Warn | Fail |
| 6 | C13 retained repair, failed origin | None | Clear | Clear | Pass |
| 7 | Same repair, successful origin | None | Clear | Clear | Pass |
| 8 | C13 variant, failed origin | `page_index` | Warn | Warn | Fail |
| 9 | Same variant, successful origin | `page_index` | Warn | Warn | Fail |
| 10 | Original `aa8502b` failed checkpoint | None | Clear | Clear | Fail |
| 11 | Original `aa8502b` successful checkpoint | None | Clear | Clear | Pass |
| 12 | Original `b7a9ee9` failed checkpoint | None | Clear | Clear | Fail |
| 13 | Bound `b7a9ee9` repair | None | Clear | Clear | Pass |

Thus B solves every observed local missing-name classification in this sample and removes A's one false warning. It does not solve all procedural semantics: rows 0, 1, 10 and 12 remain executable/name-correct failures. Nothing establishes that learning has information inaccessible to a competent static/manual checker: proposed task, API, code and presence observations can be shared. Additional historical contrast changes the learned decision rule, not entitlement to privileged runtime facts. [Exact identities and confusion matrices](056_CYCLE22_STRICT_DECISION_REPORT.md).

### 4.3 Native repair and the fixed-pair activation ceiling

The eleven pairs below come from already saved branches. They are not eleven independently collected tasks. `Y0` is original native success; `Y1` is edited native success. Native API counts do not include provider token costs or human work.

| Original row → edit row | Y0 | Y1 | Fixed manual risk decision | Native API original → edited |
|---|---:|---:|---|---:|
| 10 → 0 | 0 | 0 | Keep original | 37 → 31 |
| 11 → 1 | 1 | 0 | Keep original | 33 → 11 |
| 10 → 2 | 0 | 0 | Keep original | 37 → 30 |
| 11 → 3 | 1 | 0 | Keep original | 33 → 10 |
| 10 → 4 | 0 | 1 | Use edit | 37 → 53 |
| 11 → 5 | 1 | 0 | Keep original | 33 → 11 |
| 10 → 6 | 0 | 1 | Use edit | 37 → 53 |
| 11 → 7 | 1 | 1 | Keep original | 33 → 33 |
| 10 → 8 | 0 | 0 | Keep original | 37 → 30 |
| 11 → 9 | 1 | 0 | Keep original | 33 → 10 |
| 12 → 13 | 0 | 1 | Use edit | 151 → 185 |

| Saved selection policy | Successes / 11 | G | H | Selected native API operations |
|---|---:|---:|---:|---:|
| No repair | 5 | 0 | 0 | 501 |
| Always edit | 4 | 3 | 4 | 457 |
| Static all-clear selector | 7 | 2 | 0 | 533 |
| Manual risk-reduction selector | 8 | 3 | 0 | 567 |
| Outcome-privileged per-pair quality oracle | 8 | 3 | 0 | 567 |

The manual policy reaches all available quality improvements and avoids all available harmful choices. A new learned selector cannot strictly beat 8/11 when choosing between these same outcomes. This does not prove manual transfer or cost optimality: it is post-hoc human logic on two scenarios, and selected API use increases by 66 over no repair. The oracle is a retrospective bound, **not an executable baseline**. [Exact selection report](../artifacts/research/post22_saved_branch_selection/reports/ddf9e80dbe78f7c935abb63c31fbaba975fcf339d7e1bb9a889029b5c87f48cb.json).

### 4.4 Cycle 24 versus Cycle 24B, per task

Every Cycle 24 proposal is strict-format invalid. All four become extractable only in the separately labeled 24B analysis. No teacher content was edited and no additional model request was sent. The teacher received no randomized contrastive-memory treatment. Its access to the exact task history and failure feedback makes ordinary debugging and hindsight strong competing explanations.

| Source / inspected task | Strict C24 | C24B native checks, original → edit | G/H | Native API operations | Input / output tokens; inherited teacher USD |
|---|---|---|---|---:|---|
| 00: `27e1026_1`, C11 r0 action 14, oldest-song task | Invalid format | 1/2 → 2/2, failure → success | 1/0 | 26 → 107 (+81) | 28,383 / 826; 0.097539 |
| 01: `3c13f5a_1`, C14 r0 action 10, bill task | Invalid format | 1/6 → 1/6, failure → failure | 0/0 | 46 → 46 | 29,439 / 272; 0.092397 |
| 02: `60d0b5b_1`, C11 r0 action 46, refund task | Invalid format | 0/7 → 0/7, failure → failure | 0/0 | 100 → 103 (+3) | 30,806 / 567; 0.100923 |
| 03: `ce359b5_1`, C14 r0 action 39, old-song removal | Invalid format | 5/8 → 8/8, failure → success | 1/0 | 176 → 190 (+14) | 46,046 / 1,181; 0.155853 |
| Total | **0/4 accepted** | **2 successes / 4 after post-hoc extraction** | **2/0** | **348 → 446 (+98)** | **134,674 / 2,846; 0.446712** |

Source 00 fixes use of release-date information; source 03 adds collection/entity handling including pagination. Source 01's authentication/interface correction does not complete the task. Source 02 removes an interface error without native goal success. These are plausible task-specific repairs; their mechanisms were not compared with an equally capable no-record debugger, success-only, reflection-only or unpaired-source generator. All four baselines failed, so H=0 cannot estimate damage to initially successful tasks. Four different scenarios are four independent scenario units, not sixteen units because of branch repetition. Native action/error details remain in the [24B proposal results](../artifacts/research/cycle24b_teacher_format_compat/proposal_results) and [completed report](../artifacts/research/cycle24b_teacher_format_compat/effect_reports/37a9059aac761ae82e8ee2c59af4acd2443bf812b741ea4015b8538a99f44df0.json).

### 4.5 Real tasks versus learned-method evidence

Real GSM8K responses and native AppWorld successes exist. Real-task execution is therefore not wholly absent. What is absent is the necessary attribution: a provenance-clean learned component, held-out independent contexts, competent information/compute-matched controls, and a causal improvement over them. Neither a repaired program, nor a successful source episode, nor a format-compatible teacher response supplies that missing comparison.

## 5. Negative and falsified findings

| Negative evidence | What it rules out | What it does not rule out |
|---|---|---|
| Synthetic procedural rules are human/domain-authored. | Using synthetic gains as proof of automatic general-purpose contract induction. | Their value as regression fixtures. |
| GSM8K outcomes vary across repeat conditions; separate upstream calls and an invalid ExpeL memory distort comparison. | A clean reproducible efficacy or baseline-superiority claim from those scores. | Possibility of a future correctly controlled method effect. |
| Cycles 2–3 have zero admitted candidates/banks despite more failures in Cycle 3. | Claim that the current contrast representation already learns useful real-task contracts. | More suitable source/representation producing candidates elsewhere. |
| Cycles 6–9 have no native successes. Format errors improve before task success does. | Treating parser success or source throughput as idea validation. | Bounded runtime improvements. |
| Infinity, `Match`, state restoration and dependency failures are retained. | Universal replay/environment fidelity and effortless reproduction. | The documented eligible subset. |
| Boundary transplants frequently lack donor inputs; 14 NameErrors in C17B. | Treating syntactic transplantation as context-valid repair. | Public binding helping particular later candidates. |
| C19 cannot fit all contextual outcomes with its code-only representation. | Sufficiency of that representation for the observed labels. | A genuinely contextual representation, if later justified. |
| B solves all observed F821 labels, and manual selection equals the fixed-pair oracle. | Name-presence novelty and any strict quality gain from another selector on the eleven pairs. | Unseen-context candidate generation or broader activation hypotheses, which remain untested. |
| Always-edit causes four harmful flips; early static/sham each harm one successful GSM8K row. | General safety of intervention or costless benefit. | Conditional local benefits of individual edits. |
| Strict teacher output: 4/4 invalid. | A successful registered C24 source protocol. | A separately reported post-hoc format sensitivity. |
| C24B has two unrepaired failures and no matched generation controls. | Claim that teacher success is contrastive learning, learned-contract value or reliable general repair. | Existence of two additional task-specific local repairs. |
| No single induced record has demonstrated prospective cross-scenario transfer. | A reusable-memory, learned-scope or broad transfer claim. | More than one isolated local repair existing. |
| Untouched custody and exact all-in budget are not established. | Execution of the killed AppWorld pilot as a clean held-out test. | A completely new design after separate approval; no acquisition is authorized now. |
| Extensive primary-source overlap. | Novelty based merely on contrast, executable rules, counterfactual replay, blame or local recovery, individually or as a generic combination. | A future precisely specified algorithmic difference, not currently established. |

Missing learned comparisons are **INCONCLUSIVE**, not fabricated measured losses. The finite fixed-pair strict-superiority claim and the representation-sufficiency claim have stronger **FALSIFIED** status because their failure follows directly from observed ceilings/collisions.

## 6. Inconclusive, paused and killed work

### 6.1 No execution should be inferred

- Cycle 20's rejected rich-observation native experiment was never run.
- Cycle 23's twelve learned-monitor requests were prepared but never sent; runtime fixtures are not generated monitors.
- CRITIC score reconciliation and Cycle 24B are post-hoc analyses, not replacement preregistered results.
- C12–22 and the manual-selector diagnostics use inspected development/build contexts. Repeats and deletions do not create a held-out sample.
- The candidate-generation pilot and its revised no-record/unpaired design were not approved and are killed in their current AppWorld configuration.
- Fresh-data A, invariant-induction B, localization C and combined B+C are conceptual directions, not empirical results. No Cycle 25 is authorized.

### 6.2 Training-source inventory and custody limits

Existing source metadata yields the following **replay-eligible automatically collected episode inventory**, before considering whether it can support a clean new scientific split. This is not a claim that all examples are independent, near-matched, or suitable for automatic induction.

| Source | Eligible successes | Eligible failures | Provenance interpretation |
|---|---:|---:|---|
| Cycles 6–9 | 0 | 31 | Automatic raw source; repeated same four scenarios; one Cycle 9 episode excluded. |
| Cycle 11 | 1 | 7 | Automatic raw source; original four scenarios. |
| Cycle 14 | 4 | 3 | Automatic raw source; four added scenarios; one episode excluded. |
| Cycle 15 | 3 | 5 | Model-written reflection plus recollection, not target-specific human repair; must remain a separately identified source condition. |
| Total | **8** | **46** | 54 eligible episodes over 8 scenarios. Successes occur on only **3 scenarios**. |
| Without reflection-assisted source | **5** | **41** | Stricter raw-source subset; still not four independent successful scenarios. |

Success provenance is C11 `aa8502b` r1; C14 `cf6abd2` r0/r1 and `287e338` r0/r1; C15 `aa8502b`, `cf6abd2`, `287e338` r2. Repetitions are distinct episodes, not distinct scenario evidence. Human-authored framework/prompts and generic onboarding, including pagination advice, already exist; an automatic-induction claim cannot imply discovery without that information.

Exclude the original ineligible C9 infinity and C14 `Match` records; authored/oracle fixture `07b42fd1`; human/research-agent repair descendants; Cycle 24 teacher repairs from the primary revised induction pool; and the eight official archive replays from a provenance-clean primary claim because of worked-example content and missing exact original request provenance. Archive episodes can remain explicitly labeled sensitivity/exploratory material. An edited descendant is not another independent natural training success. Source counts alone do not certify four usable matched successes and failures at the needed boundaries.

**Untouched allocations affirmatively certified from the existing custody evidence: zero.** The records reserve development `29caf6f`, `82e2fac`, `6ea6792`, `76f2c72`; audit `3c90173`, `2229360`, `ae85d92`; and evaluation `ccb4494`, `2a163ab`, `34d9492`, `7d7fbf6`. These identifiers are metadata, not a claim that their payloads are clean. Reserved/not-run does not demonstrate absence of prior human, research-agent, prompt/gate-development, external-copy or template-level exposure. Missing per-file access history remains unknown; no additional reconstruction is authorized.

The manual inspector was authored after inspecting the known fourteen records on two scenarios. No affirmative evidence establishes its independence from every proposed target/template. Lack of a logged reserved-task access is not affirmative independence. These custody limits are sufficient to preserve KILL even if more raw training episodes exist than a previous informal summary suggested.

### 6.3 Budget and future-proposal corrections, retained as constraints only

The rejected design's historical estimate, 44 calls × 12,288 input and 2,048 output tokens at its archived USD 3/15 per million rates, is USD 2.973696 for that generation slice. Adding its USD 2 acquisition allowance, USD 0.50 development allowance and USD 0.50 margin gives **USD 5.973696**, already above USD 5. These are allowances, not certified upper bounds on obtaining enough qualifying fresh sources, native execution, scoring or retries. A 1,024-token cap has no universal schema-sufficiency proof in the records. Therefore **no minimum safe all-in budget is currently certifiable**; neither USD 5 nor USD 6 is an authorized safe complete pilot budget. A spend cap can stop an incomplete experiment; it does not bound the resources needed to finish one.

Any future independently approved proposal must retain, not silently relax, these user corrections:

1. Contrastive and unpaired arms share an independently frozen example permutation; only contrastive receives a separate relation map. Pairing must not leak through adjacency, IDs, timestamps, metadata, cross-references or unequal formatting.
2. A no-record zero-shot debugging arm receives identical public checkpoint information. Primary contrasts include contrastive versus no repair and versus no-record generation, not only a weak memory baseline.
3. GO requires at least two genuine `Y0=0 → deployed success` beneficial flips across at least two independent scenarios. Repeated checkpoints in one episode remain correlated. This is necessary, not by itself sufficient to establish contrast-specific value or publishability.

These are constraints preserved from conversation, not a revived protocol, new registration or proposal to execute.

## 7. Baseline and benchmark status

No full published-score reproduction of a literature baseline has been completed. Executing an unchanged component is narrower than faithfully reproducing a whole method. “Adaptation” below is deliberate: common transport, prompts, task interfaces or bootstrap behavior differ. Equal maximum caps are not equal actual compute or usable information.

| Baseline / control | Fidelity and actual execution | Information / compute and observed result | Fairness or remaining gap |
|---|---|---|---|
| No memory / no repair | Experimental control; executed synthetic, GSM8K and saved native branches. | Normal task/public inputs; no memory. Saved eleven-pair no repair: 5/11. | Historical GSM8K plans differ across arms. Saved-branch no repair is not a new live policy rollout. |
| Success-only | Control; synthetic/GSM8K adaptation executed; unseen native pilot not executed. | Successful records only; early calls differ from other arms. | Must match source amount, model, context, candidate count and actual token allocation before causal comparison. |
| Textual rules/reflection memory | Control/adaptation; synthetic and Cycle 1 executed. | Advice rather than executable enforcement; Cycle 1 8/8. | Empty/no-op executable arm and small ceiling sample do not show superiority. |
| Static domain verifier / sham | Human-authored control; executed synthetic, C1/C4. | Designed task-specific rules or sham warning/intervention; C1 each 7/8, G0/H1. | Human logic must be reported; not an automatic-learning baseline. |
| Static A/B | Unchanged Ruff F821 configurations; control, executed C22. | Same code; B additionally receives exact public present names; 14-label confusion matrices in Section 4. | NameError detection, not full semantic verification or recovery. |
| Manual semantic inspector / risk selector | Human-authored, post-hoc control; inspected saved outputs. | Code/API semantics and public context; 8/11 selected successes at 567 native API operations. | Development ceiling only. Do not weaken it to create learned headroom or claim independent test transfer. |
| Always edit / all-clear selector | Controls; offline policy evaluation on saved branches. | Same candidate outcomes; 4/11 and 7/11, respectively. | Not independently recollected agent trajectories. |
| Per-pair outcome oracle; authored native oracle | Privileged references, not deployable baselines. | Quality maximum 8/11; C5 task-specific oracle 5/5 checks. | Uses outcome privilege or authored solution logic; excluded from automatic induction. |
| No-record one-shot debugger | Essential zero-shot control; specified in rejected pilot, NOT executed as a matched arm. | Same model/public checkpoint, no source record, one repair. | C24 resembles task-specific debugging but is not a randomized matched no-record comparator. |
| Information-matched unpaired source | Essential control; NOT executed. | Same examples, actual token budget, calls, schema and frozen permutation; no relation map. | Independence from hidden pairing channels never experimentally established. |
| Failure-only / reflection-only generation | Proposed causal control; matched pilot NOT executed. | Failure context only, matched generation resources. C15 recollection used a critic but is not this comparison. | No demonstrated contrastive gain over a strong reflection repair. |
| Equal-compute retry/resampling | Required control, not a completed matched native comparison. | Same total generation/verification calls and budgets. | More successful repairs with extra compute would not identify contrast or contracts. |
| ExpeL | GSM8K prompt adaptation executed, result invalid; official pinned components smoke-tested, not full reproduction. | Historical 40 task calls, USD 0.002091654616; 14/20 unusable due literal `None` memory. Later three CLI starts, six parser/update and seven retrieval checks. | Environment/LLM constructor bypass and tokenizer fixture in retrieval checks; no native insight/policy result. [Progress](019_EXPEL_NATIVE_REPRODUCTION_PROGRESS.md). |
| AWM | GSM8K offline workflow adaptation executed; unchanged official scorer component fixture. | Historical 17/20; 40 task calls, USD 0.002429511878. Fixture 50% element, 75% action F1, 50% step/task success. | Fixture scores are authored expected outputs, not Mind2Web benchmark performance. [Status](BENCHMARK_BASELINE_SHORTLIST.md). |
| CRITIC | Paper-inspired arithmetic/tool-feedback adaptation, not exact reproduction. | Historical 60 task calls, USD 0.004298991026; 8/20 original, 17/20 post-hoc reconciliation with no new calls. | Different compute and null-correction semantics; both results preserved. |
| AutoGuide | Essential proposed adapted baseline; NOT implemented or run. | Context-aware contrast-derived guidance. | No integration, matched budget or reproduction score. [Priority revision](BENCHMARK_BASELINE_SHORTLIST.md). |
| ReasoningBank | Official source/component audit; NOT full native retrieval/policy reproduction. | 97 files syntax-parsed; ten lifecycle fixtures repeated using toy embeddings and bypassed startup; no model calls. | Embedding/cloud environment and cache mutations remain adaptation concerns. [Audit](029_REASONINGBANK_OFFICIAL_SOURCE_AUDIT.md). |
| CONTRAMEM | Proposed baseline; primary paper inspected; official implementation provenance not certified. | Matched success/failure procedural cards; no local result. | Any code reconstruction must be labeled paper-based reimplementation, not exact reproduction. |
| Skill-Pro | Proposed baseline; paper and linked source identified, not integrated or run. | Skill validation/gating, not assumed equivalent to executable predicates. | Gate/transport/task fidelity unverified locally. |
| AgentSpec | Pinned native parser/Rule and exact interpreter-body fixtures; no full policy reproduction. | Eighteen repeatable probes and four container probes over two fixtures; no real recovery/model calls. | Bootstrap bypass, grammar/dispatch discrepancies and unresolved full environment disclosed. Include both manual and generated-rule variants in any future comparison. [Audit](040_AGENTSPEC_PINNED_PARSER_AND_ENFORCEMENT_AUDIT.md). |
| ERL, ASI | Reserve proposed methods; NOT integrated or executed. | Single-trajectory reflection / reusable-skill alternatives in prior shortlist. | No local information/compute matching or scores; future implementations would need explicit fidelity labels. |
| Raw episodic/full-trajectory memory | Proposed control in the original task; not a completed matched native benchmark arm. | Retains raw histories; context and retrieval costs matter. | Do not substitute AWM or success-only and claim this exact control was run. |
| Daikon, ICE/Horn-ICE, one-shot LLM invariant induction | Proposed B-direction static/induction comparators; NOT implemented as matched arms. | Likely invariants; counterexample/implication learning; prompted specification induction, respectively. | Different oracle and trace assumptions require explicit adaptations; no local results. |
| Outcome Monitors / tools-only; Contract2Tool | Proposed monitor/tool-access controls, not local reproductions. | Monitor receipts or tool contracts; public recovery/tool list must be matched. | Tool availability alone is a strong competing cause of recovery. |
| Who&When, AUDITA, CAR, C3, CausalFlow, DoVer | Literature comparators for attribution/repair; no local reproductions or scores. | Log localization, duty-aware blame, counterfactual responsibility or intervention repair; differing feedback and compute. | A future port would be an adaptation unless all native assumptions/protocols are reproduced. Ground-truth annotations are not causal oracles. |
| AgentTether, SymTrace/SymFail; CHIEF/DCFA discussed comparators | Proposed recovery/localization comparisons only; NOT implemented or evaluated locally. | Runtime diagnostics, boundary interventions, resampling/repair or failure attribution. | No verified equal-compute local comparison; discussion is not reproduction. |
| B-only / C-only / combined B+C; targeted versus whole-team retry | Proposed ablations and recovery controls, NOT implemented. | Would isolate induction, localization and recovery, holding interfaces and compute constant. | No approved algorithm, frozen cost or experiment. |

The historical 20-task literature run additionally used 48 CoPro task calls costing USD 0.002599017544; the four methods account for 188 task calls, with the remaining 22 calls for construction. Its 210-call total must not be interpreted as equal per-arm compute.

The four initial benchmark families were **AppWorld, WorkArena++, SWE-bench and ALFWorld**, a shortlist rather than an executed suite. AppWorld has a bounded adapter but its current scientific allocation is killed. ALFWorld has one native environment component gate, not a full paired-checkpoint comparison. WorkArena++ and SWE-bench lack an integrated evaluated adapter in this record. Later fresh-data discussions mention SWE-smith/repository repair, tau2-style shared-control tasks, AssetOps/The Agent Company workflows and PARTNR-like collaborative planning; none was acquired or executed as this project's replacement. Their fresh custody, state restoration, native scoring and adaptation costs remain unestablished. [Original shortlist and append-only updates](BENCHMARK_BASELINE_SHORTLIST.md).

## 8. Reproducibility and engineering snapshot

### 8.1 Git and preservation

| Snapshot | Observation |
|---|---|
| Branch | `codex/copromem-research-loop` |
| HEAD at start of this reporting task | `18025102c010e85f26b0b3fb1144a1cb684b587e` |
| Initial user worktree | 18 modified tracked files and 24,808 untracked paths in the full status listing; no deletion reported. The files belonged to the user and were not cleaned or reset. |
| External change while this report was being prepared | HEAD became `dbd314f85b6eaedf8c956198e1e2c3ba822af504`, timestamp `2026-09-16T21:16:35+07:00`, subject `research checkpoint`. This reporting agent did not create that commit. |
| Last pre-write snapshot | Same branch; HEAD `dbd314f85b6eaedf8c956198e1e2c3ba822af504`; clean Git status, 24,847 tracked entries. The external commit contains 24,826 changed files, 882,140 insertions and 228 deletions. |
| Report output | Two new Markdown files only; no commit, push, reset, merge, deletion or experimental modification by this reporting task. |

The initial modified paths were `.gitignore`, `README.md`, `pyproject.toml`; `src/copromem/{bank,contracts,experiment,literature_baselines_experiment,metrics,real_gsm8k_experiment,replay,synthesis,synthetic,tiny_experiment,types,workflow}.py`; and `tests/{test_contract_system,test_literature_baselines_experiment,test_real_gsm8k_experiment}.py`. Their change during this task was a Git checkpoint event, not a report-driven rewrite. All 69 pre-existing root research Markdown hashes remained unchanged across that event. A current HEAD cannot automatically reconstruct every early uncommitted implementation used in historical experiments.

Protected existing document SHA-256 values:

- `docs/CoProCon_research_doc.md`: `1C8D63B16079F9CA96EC2E690CDABA31118DF6751A178BC9CDB394F1FD3BA73A`.
- `docs/CoProCon_research_doc.docx`: `AF2ACF33C597E014482889CF731B75D293ED9B3FB0C0FCFF5A7FDFBC5F3CB5C3`.

### 8.2 Tests, lint, dependencies and baseline pins

The last explicit completed full-suite statement found is **473 passed**, in [the saved-branch result](061_SAVED_BRANCH_SELECTION_RESULT.md). Earlier records report 404 and 415 at their corresponding revisions. The current pytest cache contains 492 node IDs and an empty `lastfailed` object; **this is not a certified 492-test full-suite pass**. Later Cycle 24 preparation includes a retained failed focused test followed by a metadata correction. No suite was rerun for the current HEAD in this report.

No global lint-clean claim is justified. A known retained scoped warning is Ruff `FURB192` in the frozen `research/scripts/run_boundary_effects.py` (`sorted(ids)[0]`). Later scoped checks do not erase that historical warning. Tests and lint were deliberately not rerun under the user's reporting-only constraint.

Main host Python is 3.13.5. AppWorld uses a Linux Python 3.12 isolated worker with pinned AppWorld 0.1.3.post1 and an 80-dependency hash-locked build. Official archived source came from a different original code/data setting; unchanged source execution is not original GPT-4o request reproduction. The bounded worker image used in later gates is `b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6`; earlier locked-worker evidence includes `c24cc87e56db2ef7a636b69c634f3b375f8c749d183e5f93ec551f0ceb1e938f`. Image/runtime promotion does not retroactively rewrite earlier failure records.

| Dependency/source | Recorded revision / state |
|---|---|
| ExpeL gitlink | `e41ec9a24823e7b560c561ab191441b56d9bcefc`, populated; isolated Python 3.9.17 component environment. |
| agent-workflow-memory gitlink | `8c0ff8cd11d648c8fceb99e4e42f37e3b75381b1`, populated. |
| ProphetNet gitlink | `5cf70eb41cdaa1d8faa3e1265d95ee5792d49a53`, still uninitialized. |
| ReasoningBank official source | `ed80611788292ea739f1effd31f16c53823b8a0d`; static/function-fixture audit, not resolved native policy environment. |
| AgentSpec official source | `e6fa3902e2cfb9681f454b355691b771f70543f8`; parser/interpreter components, not a complete native dependency installation. |

`.gitmodules` URL metadata was restored earlier and is present at the current checkpoint. Existing `.env` credentials were not read or copied for this report. Saved benchmark responses can contain simulated account data; that is not reproduced here and should not be confused with permission to publish raw artifacts without review.

### 8.3 Frozen evidence and identity

The stores preserve configuration/protocol JSON, source snapshots or hashes, requests/prompts, raw responses and usages, episode action/observation traces, replay reports, native scorer outputs, and reservation/settlement records where that scheme existed. Coverage is strongest for the research-loop stores and weaker for legacy runs and external archives. Not every historical environment/request can be recovered from a current source tree.

| Key frozen evidence | Digest / location |
|---|---|
| C12 crossover | `669e67cf8164c3cd4e31d0e029bc3c4069ca26436ff17d9b5ac4cea0956aea5a`, [store](../artifacts/research/cycle12_action_crossover). |
| C13 procedural edit report | `3b804f5a064696081627852d0eb3046e761a7dae49ec410d8ecb92d1da2a166d`, [store](../artifacts/research/cycle13_procedural_diff). |
| C18 bound native effects | `41f762eab2b0f87b9088e6c9234986d00c4b94245b6d87aa8a09b3bf7a6b5465`, [store](../artifacts/research/cycle18_bound_effects). |
| C22 checker report / repeat audit | `44089b0c774a60e7f942675dbccb0b77e3d2e81f6fdeb68af51205a8383dfe8a` / `29a92ada86516322f635750c6d685e2dc6d6190cc59834f5f5471b071cf16fa5`, [store](../artifacts/research/cycle22_static_name_check). |
| C23 isolated sandbox | `d2061cd58e5acc90e5354af9d3ad3ca4cf234218ee1a1d9a0c26ee2b935948ed`, [store](../artifacts/research/cycle23_monitor_sandbox_preflight). |
| Manual selection report | `ddf9e80dbe78f7c935abb63c31fbaba975fcf339d7e1bb9a889029b5c87f48cb`, [store](../artifacts/research/post22_saved_branch_selection). |
| C24 strict protocol / proposal report | `bc4ee11f08d444cc03f4daf12437060ffa035fd5793b88d09152d8fde62b66a5` / `95964b682326d291f23b30e651f9e4bc46c96e2f3991a2a0c276e1c2614d2971`, [store](../artifacts/research/cycle24_teacher_repair_source_v2). |
| C24B protocol / completed native effect report | `335692049e8c3d0249f7f9d7001faf7e4826ee4010ab20a8da183d18c3f146ad` / `37a9059aac761ae82e8ee2c59af4acd2443bf812b741ea4015b8538a99f44df0`, [store](../artifacts/research/cycle24b_teacher_format_compat). |

Checkpoint identity binds source episode, planner/action boundary, permitted public observation and saved continuation under the recorded protocol. Repeating the same state reconstruction and action stream checks implementation fidelity. It does not create independent observations, certify secret-state completeness for unsupported values, certify unseen data, or establish causal credit for a particular agent. Source snapshots with actual text are stronger than a bare HEAD/hash; both remain available where recorded.

### 8.4 Report-only consistency verification

After creating both new reports, all 192 local Markdown link targets across them resolved to existing paths. The 69 pre-existing root research Markdown files and 165 sampled source/test/script/configuration files retained their pre-report SHA-256 values; both protected original research documents also retained the hashes listed above. Git status showed exactly the two new report files and no tracked modifications. No tests, lint, native benchmark actions or experimental provider requests were run for these checks. The external checkpoint commit described above is separate from these report-only changes.

## 9. Cost reconciliation

### 9.1 Canonical research-loop accounting

The canonical accounting mechanism is the distributed append-only `reservations`, `settlements` and `calls` records in each paid research store, interpreted by [BudgetLedger](../src/copromem/providers.py). No separate complete global billing ledger was found. The reconciliation sums settled `actual_usd`; an unsettled attempt contributes its conservative reservation to charged/reserved exposure. “Settled” here means the local usage-based ledger, not independent reconciliation against a provider invoice.

| Store under `artifacts/research/` | Completed calls | Attempts | Input tokens | Output tokens | Settled USD | Unsettled reserved USD |
|---|---:|---:|---:|---:|---:|---:|
| `cycle01_paired` | 54 | 54 | 11,752 | 6,270 | 0.00152572 | 0 |
| `cycle02_induction` | 72 | 72 | 12,977 | 9,168 | 0.00209930 | 0 |
| `cycle03_induction` | 72 | 74 | 11,731 | 9,446 | 0.00153115 | 0.00106050 |
| `cycle06_appworld_source` | 240 | 240 | 808,122 | 62,915 | 0.06122978 | 0 |
| `cycle07_appworld_source` | 240 | 240 | 927,406 | 13,934 | 0.05485080 | 0 |
| `cycle08_appworld_source` | 240 | 240 | 957,504 | 11,495 | 0.09919890 | 0 |
| `cycle09_appworld_source` | 234 | 234 | 884,103 | 10,731 | 0.19375710 | 0 |
| `cycle11_appworld_source` | 334 | 334 | 2,058,891 | 20,335 | 0.44051750 | 0 |
| `cycle14_appworld_source` | 434 | 434 | 4,134,270 | 34,043 | 0.92504400 | 0 |
| `cycle15_reflection_source` | 544 | 544 | 5,063,748 | 29,821 | 1.07711820 | 0 |
| `cycle24_teacher_repair_source_v2` | 4 | 4 | 134,674 | 2,846 | 0.44671200 | 0 |
| **Total** | **2,468** | **2,470** | **15,005,178** | **211,004** | **3.30358445** | **0.00106050** |

**Canonical charged/reserved exposure: USD 3.30464495.** Every store's completed raw-call USD sum equals its settlement sum under decimal arithmetic; no orphan settlement was found. The two unresolved Cycle 3 reservations are `1789515119358024800` (USD 0.00048850) and `1789515190650158700` (USD 0.00057200). They are conservative unresolved exposure, not evidence that these amounts were actually billed. No provider billing query was made.

### 9.2 Historical and unpriced costs

- The nine legacy GSM8K reports in Section 3 total **675 reported calls / USD 0.041296001974**. They predate the per-attempt ledger and lack equivalent settlement certification. Do not silently omit them or describe them as canonically settled.
- Arithmetic of known reported paid costs is **USD 3.344880451974** = canonical settled plus legacy reported. Including unresolved reserves gives **USD 3.345940951974**. These are combined known-record subtotals, **not complete lifecycle cost or an invoice-certified total**.
- Official archived GPT-4o source generation has unknown original request/token/billing cost; the current project did not generate those historical calls. External acquisition work, local download/storage, dependency building, embeddings, Docker/native scoring, CPU time and human/research-agent effort have no complete USD conversion.
- No source acquisition, development, candidate generation, native execution, scoring and meaningful-margin total for the killed future pilot can be certified from the existing records. Its minimum safe complete budget is unknown, not zero.
- Cycles 4, 5, runtime-only 6, 10, 12, 13, 16–23; boundary/manual diagnostics; baseline component probes; and Cycle 24B used zero new experimental provider calls where reported. Their reused calls and local costs must not be counted as free or double-counted as new API charges.
- This reporting task made zero experimental provider/model requests and executed no native benchmark actions. Literature browsing and local reading are not a paid experimental treatment.

### 9.3 Apparent discrepancies resolved without choosing favorable numbers

1. Older “total” USD 2.85687245 settled / 2.85793295 charged-reserved was correct through Cycle 15. Adding Cycle 24 once yields the current canonical figures; 24B adds no provider cost.
2. Seventy Cycle 1 logical requests include sixteen cache hits: only fifty-four physical calls were charged.
3. Cycle 3 has seventy-four attempts but seventy-two completed calls, with unresolved reserves; completed-call count is not attempt count.
4. CRITIC's 8/20 original and 17/20 reconciled scores refer to different postprocessing analyses of the same paid run. Neither creates another USD 0.013183364132 charge.
5. The older strict-format result and later 24B effect result answer different questions. Neither can be substituted for the other to improve the narrative.
6. API-operation counts such as +16, +34 and +98 are AppWorld native operations, not OpenRouter calls or dollar amounts.

## 10. Literature and novelty status

The following are primary sources inspected for this report or in the preserved primary-method audit. Publication status is stated conservatively as of 16 September 2026: a recent arXiv manuscript is not described as peer-reviewed without verified venue evidence. These papers were not reproduced by this reporting task. Findings below concern overlap, not an assertion that every system implements exactly the same method.

| Primary work; verified status | Closest overlap and implication for this project |
|---|---|
| [ExpeL](https://arxiv.org/abs/2308.10144), AAAI 2024; [pinned official contrast prompt](https://github.com/LeapLabTHU/ExpeL/blob/e41ec9a24823e7b560c561ab191441b56d9bcefc/prompts/templates/human.py) | Experience-derived insights already include comparing same-task success/failure. Contrastive textual lessons alone are not a novelty delta. Executable, validated scope would require a demonstrated additional mechanism. |
| [AutoGuide](https://proceedings.neurips.cc/paper_files/paper/2024/hash/d8efbb5dd415974eb095c3f06bff1f48-Abstract-Conference.html), NeurIPS 2024; [method](https://arxiv.org/html/2403.08978v2) | Context-aware guidelines from trajectory deviations/shared task context overlap both near-match contrast and scoped advice. Calling a conditional textual rule a contract does not distinguish CoProCon. |
| [AgentSpec](https://arxiv.org/abs/2503.18666), ICSE 2026; [method](https://arxiv.org/html/2503.18666v3) | Executable runtime constraints with intervention, including a generated-rule study, make a manual-only characterization inaccurate. Must compare both rule quality and enforcement under equal information. |
| [Outcome Monitors](https://arxiv.org/html/2608.19303v1), August 2026 preprint | Monitors mined from traces/public schemas and advisory recovery feedback closely overlap executable process guidance. Its tool-availability ablation makes extra recovery-tool access a mandatory competing explanation, not evidence that learned detail is the cause. |
| [Contract2Tool](https://arxiv.org/html/2606.07904v1), June 2026 preprint | Normalized symbolic preconditions, effects, risk and cost from documentation/schemas/traces already cover tool-contract induction and downstream filtering. Its controlled synthetic/gold-trace setting is not a native multi-agent recovery result; that difference alone does not prove our novelty. |
| [DoVer](https://arxiv.org/html/2512.06749v3), preprint first posted December 2025; venue not verified here | Active verification of message/plan interventions and targeted repairs overlaps causal debugging. Multiple independent repair points undermine a simplistic unique responsible-agent label. B+C cannot claim novelty merely for testing local repairs. |
| [CausalFlow](https://arxiv.org/html/2605.25338v1), May 2026 preprint | Step-level causal interventions and minimally targeted corrections already connect responsibility with repair; wrong/correct evidence further reduces a generic contrast-plus-recovery claim. |
| [CAR](https://arxiv.org/html/2606.08275v1), June 2026 preprint | Causal contribution/responsibility estimation with same-policy counterfactuals, interactions and budgeted sampling overlaps credit assignment. A local successful intervention is not automatically a calibrated responsibility score. |
| [C3 / Exact Is Easier](https://arxiv.org/abs/2603.06859v2), 2026 preprint | Fixed histories, alternative actions and fixed downstream behavior support controlled agent comparisons. Its text-state assumptions are not automatically a complete AppWorld database/Python-state model. One stochastic continuation does not become an exact population causal effect. |
| [AgentTether](https://arxiv.org/html/2607.06273v1), July 2026 preprint | Dependency/transition representations, learned anomaly priors, diagnostic guidance, repair memory and guarded runtime together strongly overlap the generic combined B+C story. A specific new induction/localization algorithm would be necessary. |
| [SymTrace / SymFail: Repair or Resample?](https://arxiv.org/html/2608.25920v1), August 2026 preprint | Boundary event graphs, intervention injection, replayed prefixes and regenerated suffixes directly test repair against resampling. Our saved open-loop suffix is a narrower estimand, not an unexplored general idea. Prefix matching alone is not end-to-end determinism in either setting. |
| [Who&When](https://arxiv.org/abs/2505.00212), 2025 primary manuscript; venue not independently certified in this audit | Agent/step failure localization from traces and annotation already exists. Annotator attribution is not ground truth for which intervention improves a task. A future comparison must separate localization accuracy from intervention value. |
| [AUDITA](https://arxiv.org/html/2608.22160v2), August 2026 preprint | Duty-aware evidence paths, cause/witness distinctions and replay-based blame overlap contract-guided responsibility. Its provided normative duties are not the same as demonstrated automatic induction of valid duties; that possible distinction remains unimplemented here. |
| [ICE](https://madhu.cs.illinois.edu/CAV14ice.pdf), CAV 2014; [Horn-ICE](https://madhu.cs.illinois.edu/HornICELearning-OOPSLA18.pdf), OOPSLA 2018 | Positive/negative/implication counterexamples and Horn constraints already support invariant/contract synthesis. “Counterexample-guided induction of contracts” is an established algorithmic family, not itself a new contribution. |
| [Contracts for Higher-Order Functions](https://users.cs.northwestern.edu/~robby/pubs/papers/ho-contracts-icfp2002.pdf), ICFP 2002; [Causality, Responsibility and Blame in Team Plans](https://www.cs.cornell.edu/home/halpern/papers/teamplans.pdf), AAMAS 2017 | Contract blame and team responsibility have formal precedents. Distinguish duty violation, causal contribution and the best repair target; they need not identify the same agent. |
| [CONTRAMEM](https://arxiv.org/html/2608.22533v1), August 2026 preprint; [ReasoningBank](https://arxiv.org/html/2509.25140v1), primary preprint version; [Skill-Pro](https://arxiv.org/html/2602.01869v3), primary preprint version | Contrastive procedural cards, success/failure strategies and validated skills cover adjacent memory mechanisms. A skill with textual fields must not be misrepresented as an executable checker, but textual-memory novelty is already crowded. |
| [Procedural Knowledge Graphs](https://arxiv.org/html/2609.09153v1), September 2026 preprint | High/low-quality traces, structured procedural refinement and rollout validation further weaken a generic “contrast plus structured reusable procedure” claim. See the preserved [novelty update](052_PROCEDURAL_GRAPHS_NOVELTY_UPDATE.md). |
| [Daikon](https://plse.cs.washington.edu/daikon/), official system; [delta debugging](https://www.st.cs.uni-saarland.de/papers/tse2002/), primary publication; [GenProg](https://web.eecs.umich.edu/~weimerw/p/weimer-tse2012-genprog.pdf), primary publication | Invariant detection, minimizing failure-inducing differences and test-validated program repair are established alternatives. A transplanted block passing task tests does not become a novel learned procedural contract solely by renaming it. |

The remaining possible distinction is narrow and conditional: automatically inducing scoped, executable **inter-agent obligations** from clean evidence, then showing that those obligations improve intervention target choice beyond equally informed static contracts and established causal debugging. This is **not yet an algorithm or a validated novelty claim**. It would require a precise representation, an induction/verification oracle with stated assumptions, and a causal separation of contract quality, localization and recovery. Simply combining B and C, or using the current repository as a scaffold, is insufficient. The audit therefore does not authorize starting B+C.

## 11. Direct scientific answers

| Question | Answer supported today |
|---|---|
| Has CoProMem demonstrated a reproducible advantage? | **No causally attributable real-task advantage.** Synthetic gains are reproducible diagnostics; historical GSM8K comparisons are unstable/confounded and include an invalid baseline. |
| Has CoProCon demonstrated learned-contract value beyond static/manual controls? | **No.** Static B handles the measured missing-name class; the manual selector saturates saved quality opportunities. No valid learned-contract comparison closes this gap. |
| Has learned activation been falsified on the available fixed pairs? | **Yes, strict positive quality superiority over the fixed manual selector on those exact eleven pairs.** No new selector can exceed the available 8/11 oracle. General learned activation remains untested, not universally disproved. |
| Is the current AppWorld configuration usable? | **Engineering artifacts remain usable for inspection; the proposed clean held-out research configuration is KILLED and not executable under current authority.** Reserved split labels do not repair custody. |
| Does proposed B+C currently have sufficient algorithmic novelty? | **Not established.** The current verbal combination has serious exact component and system-level overlap. There is no demonstrated new algorithmic delta. |
| Strongest defensible contribution now? | An evidence-backed diagnostic/negative case study and bounded reproducibility assets: interface/source confounds, static-control strength, local native repair opportunities, and the activation ceiling. This is not yet a demonstrated publishable AAMAS method advantage. |
| What is needed before an AAMAS submission? | A real coordination/interaction hypothesis rather than relabeled single-agent debugging; a precise novelty difference over Section 10; prospectively clean independent train/dev/test evidence; strong static/manual, no-record, reflection and equal-compute comparators; separate induction/localization/recovery metrics; harms, transfer and lifecycle accounting; and a decisive held-out result. None is guaranteed by the current code. |

## 12. Exact stopping point

Keep paused: the autonomous research goal; all paid calls and native experiments; Cycle 23's proposal run; any activation fitting/tuning/evaluation on the eleven pairs; any alteration of the existing manual gate; reuse or rehabilitation of the killed reserved AppWorld allocations; additional provenance reconstruction; fresh data acquisition; further numbered cycles; and B+C implementation. Do not register a new pilot as an extension of the killed configuration.

Retain without promoting: the current code checkpoint, original strict and post-hoc reports, failed protocols, component fixtures, raw outputs, cost ledgers and local repair evidence. Do not rewrite the original research document into a success narrative.

**Recommended next decision: accept the current configuration's termination and review this evidence before deciding whether the broader line merits a genuinely new conceptual proposal.** Continue only if a precise novelty difference and an independently falsifiable, affordable clean test can first be defended on paper. If that difference is merely prompting, ordinary debugging, interface correction, additional tool access or extra compute, terminate the broader learned-contract claim rather than build more infrastructure. No experiment is recommended merely because it can be constructed.
