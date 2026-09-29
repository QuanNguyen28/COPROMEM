# v6.2 Evaluation 002: clean successor allocation

Evaluation 002 is a separately frozen clean successor to immutable,
infrastructure-failed Evaluation 001.  It begins at 0/300 and imports neither
an Evaluation 001 score nor a memory-state update.  The failed run's USD
0.00147015 is carried only within the historical infrastructure exposure.

The allocation was generated before payload access from the public
`test_normal` inventory using the existing family-round-robin algorithm.  The
only hard-excluded ID is `024c982_1`, which has durable worker, action,
response-attested, scorer, and executor-settlement evidence in Evaluation 001.
There are 137 eligible IDs after this exclusion; 30 are selected, retaining
one ID from each of the first 30 canonical public families.

* Inventory hash: `33f1018e3a57154784b2859a20e3c8d801fdb1634c6aec6a7fce6180e5e63ee9`
* Candidate-list hash: `ddd656375f6469702d3c085198d51103e9ac00d3ddf12a6e810f41f346100f94`
* Selected-ID hash: `15ddbae1f003ece12fed344d43a4d9be0e30961c532129aa596d65b3cbe53499`
* Public callable-registry hash: `09325ae59f351b4b18ae5127a456890c844515b872277ba4c133ffbd9c5c4423`
* Ordering: family ID ascending, task ID ascending, round-robin by family
  occurrence.

Selected public IDs:

`024c982_2`, `042a9fc_1`, `09b0ee6_1`, `0a9d82a_1`, `0d01c76_1`, `0de03ea_1`,
`1150ed6_1`, `13547f5_1`, `166f4ff_1`, `21abae1_1`, `270f1ff_1`, `29a7b7e_1`,
`2c544f9_1`, `2d9f728_1`, `31dc501_1`, `325d6ec_1`, `32616b5_1`, `3aa1a22_1`,
`3b8fb7a_1`, `3d9a636_1`, `425a494_1`, `522e5e5_1`, `552869a_1`, `59fae45_1`,
`5a83b05_1`, `634f342_1`, `652485c_1`, `6b6ca61_1`, `6f4b9a5_1`, `7847649_1`.

This is compatibility-conditioned exploratory sampling, not an unbiased held-
out benchmark sample.  The frozen evaluation has five arms, two stochastic
trials, and 300 maximum trajectories under the existing USD 300 hard cap.
