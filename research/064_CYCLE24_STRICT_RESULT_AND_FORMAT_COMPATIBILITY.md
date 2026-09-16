# Cycle 24 strict result and pre-native format-only compatibility pass

Recorded 2026-09-16 after all four fixed teacher requests finished, before any
teacher-proposed program was executed. No request is repeated or replaced.

## Original strict result, retained

All four provider calls completed with `finish_reason=stop`, but every raw answer
had commentary outside its JSON object, so the registered whole-response JSON
parser rejected all four with `JSONDecodeError`. The strict accepted-proposal
count is **0/4** and its native source gate cannot pass. This is an output-interface
failure, not an observed native repair failure or a negative learned-memory result.

Settled and charged/reserved cost are both USD **0.446712**, four HTTP attempts,
zero transport failures or unsettled reservations. The source protocol is
`bc4ee11f08d444cc03f4daf12437060ffa035fd5793b88d09152d8fde62b66a5`;
strict proposal report is
`95964b682326d291f23b30e651f9e4bc46c96e2f3991a2a0c276e1c2614d2971`.
Its store, raw responses, invalid statuses, candidate parser and protocol remain
unchanged. The earlier preflight metadata failure is also preserved separately.

The official selected route lists Sonnet 4.6 at USD 3/M input and 15/M output;
the experiment pins Anthropic and disables fallback and reasoning, with no
unsupported seed parameter. [Official model/route information](https://openrouter.ai/anthropic/claude-sonnet-4.6).
This source-policy change is not an otherwise matched teacher-model comparison.

## Compatibility rule, specified before native effects

Inspection finds exactly one complete JSON object with the required three keys
in each answer. Run one transparent **format-only sensitivity pass**:

1. Scan the raw response with the standard JSON decoder.
2. Require exactly one complete object with exactly action_index, code, diagnosis.
   Reject zero or multiple matches; do not select among alternatives.
3. Feed that EXACT object substring to the unchanged strict proposal parser,
   including duplicate-key rejection, target bounds and original worker policy.
4. Preserve raw response digest, object byte/character span, surrounding-text
   digests, decoded code digest and candidate provenance. No code token, target
   index, diagnosis, API argument or algorithm is edited or generated again.
5. Run all resulting valid proposals with factual controls through the original
   saved-continuation engine. No selection uses native outcomes. Any null/unsafe
   proposal remains in the complete four-task denominator.

This changes acceptance of response envelopes AFTER seeing those envelopes;
it is explicitly not the original strict-format result. It does not change
teacher content, constitute syntax repair, add native feedback, permit a retry,
or turn a source experiment into a learned-contract test. Label the resulting
report Cycle-24B compatibility sensitivity, separately from strict Cycle 24.

Reuse the existing image, worker, scorer, original prefix/settings/future actions,
cost ledger and teacher responses. At most sixteen native runs/scorers remain
possible. New API/model calls are prohibited in this compatibility script.
Keep all failures and verify the exact original checkpoint for each pair.

If a compatible patch succeeds, inspect whether it is merely pagination,
authentication/interface correction, task-specific hindsight or a distinct
procedural mechanism. None automatically establishes learned value, novelty,
scope generalization or a viable research pivot. Do not weaken a future manual
control based on whichever teacher patch happens to pass.
