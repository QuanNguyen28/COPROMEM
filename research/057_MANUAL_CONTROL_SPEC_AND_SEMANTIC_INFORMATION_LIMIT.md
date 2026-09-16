# Post-gate finding: the paused semantic-verifier inputs lose decisive information

Recorded 2026-09-16 after the strict Cycle-22 decision. This is one bounded
public-code/API inspection and two constructed counterexamples, not a resumed
Cycle-23 run or an expanded audit platform. No new native or model call occurs.

## Public evidence for the manual procedural control

The two source instructions both require **all** relevant artists. The saved
public API documentation specifies page index 0 and page limit 5 by default
for both `spotify.show_liked_songs` and `spotify.show_playlist_library`; the
maximum permitted page limit is 20. Both original failed actions omit pagination
arguments. Both retained repairs replace a single first-page request with
collection accumulation over advancing pages. Thus the same documented
pagination pitfall explains the changed producer mechanism in both cases.

A competent manual reference specification for this fixed task family is:

1. Preserve the full-set obligation from the public task; do not silently treat
   one page as the complete requested collection.
2. Traverse the documented page sequence, accumulate all retrieved items and
   reach a justified terminal condition. A mere `while` node is not evidence of
   coverage: advancement, accumulation, early exits and the actual producer/
   consumer connection matter.
3. Apply the task's actual genre predicate and include **every** artist of each
   qualifying song, not only its first artist.
4. Preserve authentication, input availability and downstream app semantics.
   Name availability remains the shared F821 component, not learned novelty.

This is a human-authored semantic specification, **not an implemented or validated
strong checker**. The docs inspected here do not by themselves prove all desired
termination/stability assumptions. In particular, the old repair's short-page
termination convention must not be upgraded into a universal guarantee merely
because it worked on the saved instance. A conservative checker may need to
abstain when the public evidence cannot establish completeness.

## A successful task is not a universally correct procedure

The original b7a9ee9 action (record 12) and its passing repair (record 13) both
contain `song_details['artists'][0]['id']`. The user asks for all artists, and
the public `show_song` response schema represents `artists` as a list, without
an inspected singleton-only restriction. Pagination repair does not change this
first-element selection.

Two hypothetical states illustrate the limit: one qualifying song with one
not-yet-followed artist, or the same situation with two not-yet-followed artists.
Selecting only the first artist covers the first state's requirement but not
the second. The code/name-presence view is identical because it does not expose
the response values. These are **constructed possible states**, not claims that
either is the actual saved benchmark database. Other artists could already be
followed in a real instance; the native success label remains true as recorded.

Consequently, requiring a semantic verifier to accept every native-success
example can conflict with conservative procedural correctness. The existing
binary code-to-saved-outcome proposal test cannot establish a universal semantic
contract. This does not rule out probabilistic prediction or benefit selection;
those need their own targets and uncertainty claims.

## Exact information loss in the paused input representation

On the actual passing record 13, replace only the comparison literal `classical`
with `__counterexample_other_genre__`. The original and changed programs are
different, and their genre predicates return opposite truth values for a
constructed classical item. Yet the frozen `runtime_input` normalizer produces
**exactly the same complete code/present-name input** for both, because it
replaces every string literal with `<string>`.

This is a concrete representation collision, not speculation about model skill.
No deterministic or stochastic monitor observing only that identical input can
reliably distinguish which original genre predicate was supplied. The altered
program was **not executed or scored natively**, so no native harmful flip is
claimed. It is sufficient to reject this representation as an information-
preserving input for genre-semantic verification.

The [evidence record](evidence/semantic_information_limits_20260916.json) contains
the actual case/program/document hashes, transformation and common input digest.
Two small tests demonstrate literal-information loss and the first-artist
counterexample without executing target programs or adding a runtime framework.

## Decision and impact on the next action

**REVISE the learning target and input contract. Do not send the paused twelve
proposal requests.** Retain the existing implementation and raw evidence, but
do not spend calls demonstrating consistency in a representation that erases
known task semantics.

Before any held-out comparison, a viable candidate must retain task-relevant
public literals, task requirements and API semantics while redacting credentials
specifically; share the same information with the manual control. Labels must
also match the claim: native success is a saved-instance outcome, not proof of
universal artifact correctness. Learning a scoped **repair-benefit/activation
policy** from paired intervention effects is a better-aligned target to examine,
with abstention under missing information, than declaring these native labels
semantic truth. Its advantage is still unproven and must beat the manual control
on common repair branches as required by the strict decision report.

Both observed producer repairs can already be described by the manual pagination
specification; they do not identify a distinct learned advantage. The new
consumer observation and exact normalization collision explain why simply
resuming the known-build fit test would not close that gap. No new benchmark,
model, broader literature search, generated candidate, contract-bank admission,
API expenditure or native intervention is added by this analysis.
