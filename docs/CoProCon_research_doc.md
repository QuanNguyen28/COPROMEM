# CoProCon Tài liệu nghiên cứu hiện tại

## Đặc tả phương pháp và báo cáo trạng thái thực nghiệm

Phiên bản ngày 16 tháng 9 năm 2026

Tài liệu này mô tả formulation, implementation, protocol thí nghiệm, kết quả hiện có, giới hạn diễn giải và kế hoạch nghiên cứu tiếp theo của hệ thống CoProCon đang được triển khai trong repository `copromem`. Nội dung được viết lại từ source code tại commit `ad53523`, các test và các artifact đã lưu trong repository. Mục tiêu là tạo một nguồn mô tả thống nhất giữa ý tưởng nghiên cứu và hệ thống thực sự đang chạy.

Kết luận trung tâm ở thời điểm hiện tại là: CoProCon đã chứng minh được tính khả thi kỹ thuật của executable procedural contract trong môi trường synthetic có kiểm soát. Verifier tại handoff, recovery routing, scope veto, admission và budgeted contract bank đều đã chạy end to end. Tuy nhiên, kết quả synthetic chưa tách được giá trị của contract được học từ trajectory khỏi giá trị của một static verifier do con người viết sẵn. Trên GSM8K với model thật, pipeline đã tạo được recovery activation và một số directional gains, nhưng contract vẫn là schema check được định nghĩa trước, chưa phải procedural contract được rút ra đầy đủ từ near matched success failure contrast. Vì vậy, engineering feasibility đã pass; central learning claim chưa pass.

## Mục lục

1. Bối cảnh và động cơ nghiên cứu
2. Phạm vi và ranh giới nghiên cứu
3. Câu hỏi nghiên cứu và giả thuyết
4. Formulation CoProCon
5. Kiến trúc hệ thống hiện tại
6. Quy trình hình thành contract
7. Thực thi contract tại handoff
8. Contract bank và quản trị vòng đời
9. Protocol synthetic
10. Protocol tiny experiment
11. Protocol GSM8K với model thật
12. Literature baseline adapters
13. Metrics và nguyên tắc đánh giá
14. Kết quả thực nghiệm hiện có
15. Diễn giải khoa học
16. Threats to validity
17. Mức độ hoàn thành của implementation
18. Acceptance criteria cho idea validation
19. Kế hoạch nghiên cứu tiếp theo
20. Ngôn ngữ claim được phép sử dụng
21. Reproducibility và artifact inventory

# 1 Bối cảnh và động cơ nghiên cứu

Các hệ multi agent thường sinh ra một chuỗi artifact quan sát được: planner tạo kế hoạch, solver thực hiện kế hoạch, reviewer kiểm tra kết quả, hoặc một agent chuẩn bị dữ liệu để agent khác tiếp tục. Nhiều lỗi downstream không bắt nguồn từ năng lực giải quyết cuối cùng mà bắt nguồn từ một handoff không đầy đủ, không đúng kiểu hoặc vi phạm một invariant mà agent sau không biết phải kiểm tra.

Các memory approach phổ biến thường lưu full trajectory, successful example, free form reflection hoặc textual workflow. Những dạng memory này có ba rủi ro. Thứ nhất, nội dung dài và chứa nhiều chi tiết không liên quan làm tăng read cost. Thứ hai, một lesson dạng văn bản không đảm bảo được thực thi tại đúng thời điểm. Thứ ba, similarity retrieval có thể đưa một lesson đúng vào một task sai scope và tạo harmful transfer.

CoProCon thay đổi đơn vị memory. Thay vì chỉ lưu nội dung để agent đọc, hệ thống lưu một procedural contract gắn với một interface cụ thể. Contract định nghĩa precondition, postcondition, executable verifier, owner chịu trách nhiệm sửa lỗi, recovery route, scope guard, counterexamples và evidence. Khi một artifact đi qua handoff, hệ thống retrieve contract phù hợp, chạy verifier và chỉ kích hoạt recovery nếu phát hiện violation.

Formulation này giữ tinh thần ban đầu của CoProMem là học từ sự khác biệt giữa trajectory thành công và thất bại, nhưng chuyển memory từ một corrective text sang một executable coordination object. Tên package vẫn là `copromem`; tên formulation nghiên cứu hiện tại là CoProCon.

# 2 Phạm vi và ranh giới nghiên cứu

CoProCon tập trung vào transfer giữa các episode. Câu hỏi của hệ thống là: sau khi quan sát các episode trước, nên lưu procedural contract nào để ngăn một lớp lỗi lặp lại trong episode sau.

CoProCon không giải quyết adaptive team selection, dynamic role routing hoặc model routing trong cùng một episode. Những chức năng đó thuộc phạm vi của ARCO. Trong toàn bộ thí nghiệm hiện tại, workflow được giữ cố định để attribution không bị trộn giữa team effect và memory effect.

Phạm vi implementation hiện tại gồm hai tầng.

- Tầng synthetic mô phỏng planner, solver và reviewer trong một bài toán data join. Tầng này dùng deterministic stochastic profiles để tạo controlled success failure pairs và kiểm tra toàn bộ lifecycle của contract.
- Tầng real model dùng OpenRouter trên GSM8K. Tầng này kiểm tra typed planning artifact, schema verifier, recovery call, usage accounting và so sánh một số memory baseline.

Ngoài phạm vi hiện tại gồm continual online learning, multi contract consolidation, learned semantic scope classifier, learned verifier synthesis trên open domain, multi benchmark canonical adapters và publication scale statistical confirmation.

# 3 Câu hỏi nghiên cứu và giả thuyết

## 3.1 Câu hỏi nghiên cứu

RQ1. Executable procedural contract tại handoff có giảm downstream error so với fixed workflow không có memory hay không?

RQ2. Contract được hình thành từ success failure contrast có tạo thêm giá trị so với success only memory, textual rule và sham retry hay không?

RQ3. Scope guard và counterexample veto có ngăn harmful transfer trên task ngoài scope hay không?

RQ4. Contract đã được admit có transfer sang template group chưa thấy và sang role profile hoặc executor khác hay không?

RQ5. Lợi ích của contract có còn tồn tại sau khi tính runtime calls, verifier cost, injected tokens và lifecycle construction cost hay không?

RQ6. Learned contract có tốt hơn một static verifier được con người định nghĩa trước hay không?

## 3.2 Giả thuyết

H1. Contract check có success rate cao hơn no memory trên task có handoff violation quan sát được.

H2. Contract check có beneficial flips nhiều hơn harmful flips khi so paired trên cùng task và cùng underlying stochastic draw.

H3. Contract check tốt hơn textual rule và success only memory vì verifier biến memory thành một executable intervention thay vì chỉ là prompt context.

H4. Scope guard giữ boundary harmful flips dưới ngưỡng admission và veto task có intentional alternative procedure.

H5. Contract đã minimize vẫn duy trì positive conditional benefit trên held out task.

H6. Nếu static verifier và learned contract có kết quả tương đương, kết quả đó hỗ trợ verifier value nhưng chưa hỗ trợ learning value.

# 4 Formulation CoProCon

## 4.1 Episode và handoff

Một episode gồm workflow cố định với các role nối tiếp nhau. Tại interface từ role i sang role j, hệ thống tạo một handoff event:

```text
H = interface source_role target_role artifact observable_state verifier_results
```

`artifact` chỉ chứa state quan sát được. Implementation cố ý không lưu chain of thought. `observable_state` chứa public task state cần thiết cho scope guard và verifier.

## 4.2 Procedural contract

Một contract được biểu diễn khái niệm như sau:

```text
C = interface precondition postcondition verifier owner recovery scope counterexamples evidence status
```

Các field implementation gồm:

| Field | Vai trò |
|---|---|
| contract_id | Định danh ổn định cho contract |
| interface | Handoff mà contract được phép áp dụng |
| precondition | Điều kiện artifact cần thỏa trước khi role sau tiếp tục |
| postcondition | Invariant mong muốn sau handoff |
| verifier_name | Tên verifier an toàn trong registry |
| owner | Role chịu trách nhiệm sửa violation |
| recovery_route | Cách route artifact khi verifier fail |
| scope_name | Tên scope guard trong registry |
| counterexamples | Các trường hợp tương tự nhưng không nên áp dụng |
| required_fields | Các clause hoặc field mà verifier kiểm tra |
| evidence | Replay, transfer, harm và cost evidence |
| status | candidate hoặc admitted |

Verifier và scope guard được lưu bằng tên và resolve qua registry. Contract bank không lưu arbitrary executable code do extractor sinh ra. Thiết kế này giảm rủi ro thực thi code không tin cậy và làm contract dễ audit.

## 4.3 Counterfactual effect

Với cùng một task và cùng underlying role behavior, hệ thống so sánh các arm. Beneficial flip xảy ra khi baseline fail nhưng contract pass. Harmful flip xảy ra khi baseline pass nhưng contract fail.

```text
net_gain = beneficial_flips minus harmful_flips
```

Trong synthetic implementation, per decision random draw được sinh từ hash của seed, task id, role và attempt. Các arm dùng cùng draw, nên khác biệt đến từ checkpoint intervention thay vì random branch khác nhau.

## 4.4 Admission objective

Contract chỉ được admit nếu đồng thời đạt:

- Replay gain so với textual rule không thấp hơn `min_gain`.
- Replay harmful flips không vượt `harm_cap`.
- Boundary harmful flips không vượt `harm_cap`.
- Transfer success không thấp hơn `min_transfer`.
- Counterexample veto accuracy ít nhất 0.95.

Default synthetic thresholds là `min_gain = 0.05`, `harm_cap = 0` và `min_transfer = 0.50`.

# 5 Kiến trúc hệ thống hiện tại

## 5.1 Typed observable records

Module `types.py` định nghĩa toàn bộ record bằng dataclass. Các object quan trọng gồm `JoinTask`, `PlanArtifact`, `SolverArtifact`, `ReviewArtifact`, `HandoffEvent`, `VerificationResult`, `RecoveryEvent`, `CostLedger`, `WorkflowRun`, `ReplayEvidence`, `ScopeEvidence` và `AdmissionDecision`.

Thiết kế dataclass không có dependency ngoài standard library và cho phép serialize state quan sát được thành JSON. `as_jsonable` chuyển dataclass, enum, tuple và collection lồng nhau thành payload an toàn.

## 5.2 Contract layer

Module `contracts.py` chứa:

- Registry `VERIFIERS`.
- Registry `SCOPE_GUARDS`.
- Schema `Contract`.
- Hàm `contract_from_failure` cho synthetic domain.
- Validation cho verifier name, scope name, required fields và owner.

Synthetic extractor hiện deterministic và domain specific. Nó chỉ tạo contract khi failure có `declared_cardinality = None` và một successful run tương ứng có cardinality đầy đủ.

## 5.3 Workflow engine

Module `workflow.py` triển khai fixed workflow planner to solver to reviewer. Mỗi run tạo plan, handoff event, verifier results, recovery events, solver artifact, review artifact và cost ledger.

`RunMode` làm rõ intervention của từng arm: no memory, success only memory, text rule, contrastive patch, sham retry, static verifier và contract check. Synthetic full experiment hiện dùng no memory, text rule, sham retry, static verifier và contract check. Tiny experiment dùng no memory, success only memory và contract check.

## 5.4 Replay và minimization

`compare_at_checkpoint` chạy bốn matched arms trên cùng task set. `minimize_by_clause_deletion` lần lượt bỏ required fields và giữ bản rút gọn nếu replay gain và harm gate vẫn đạt. Claim hợp lệ chỉ là empirical one minimal trong contract language và deletion set đã thử.

## 5.5 Synthesis và scope evaluation

`localize_handoff_failures` giữ các failure có incomplete plan. `propose_contracts` nhóm trajectory theo `group_id`, sau đó contrast failure với success trong cùng group. Candidate được deduplicate theo `contract_id`.

`evaluate_scope_and_counterexamples` chạy contract trên in scope dev tasks và boundary audit tasks. Nó đo in scope coverage, in scope success, boundary harmful flips, veto accuracy và transfer success với transfer role profile.

## 5.6 Contract bank

Contract bank retrieve theo interface và scope eligibility. Candidate được xếp theo conditional benefit, sau đó ưu tiên contract nhỏ. Read budget và verification budget được kiểm tra trước khi contract được chọn.

Admission enrich contract với replay và scope evidence. Storage budget enforcement giữ contract có conditional benefit cao và footprint nhỏ. Bank hỗ trợ save và load JSON mà không serialize arbitrary executable function.

Default budget synthetic:

| Budget | Giá trị |
|---|---:|
| Storage | 1000 token proxy |
| Read | 180 token proxy |
| Verification cost | 2.0 |

# 6 Quy trình hình thành contract

Quy trình research lý tưởng của CoProCon gồm chín bước.

1. Thu thập nhiều trajectory trong fixed workflow.
2. Xác định trajectory success và failure trong cùng procedural family.
3. Localize first observable handoff divergence.
4. Contrast valid artifact với invalid artifact.
5. Đề xuất typed contract candidate trong vocabulary an toàn.
6. Replay matched checkpoint với no memory, textual control, sham retry và contract intervention.
7. Minimize clause set trong phạm vi đã định nghĩa.
8. Kiểm tra transfer, boundary harm và scope veto.
9. Admit contract kèm evidence nếu toàn bộ gate pass.

Synthetic implementation thực hiện đầy đủ chuỗi trên ở dạng bounded deterministic extractor. Real GSM8K implementation hiện mới thực hiện một phiên bản yếu hơn: thu build runs, đếm failure có schema violation, đếm successful valid handoff và admit một schema contract được định nghĩa trước nếu cả hai loại evidence cùng tồn tại.

# 7 Thực thi contract tại handoff

Tại runtime, CoProCon không đưa toàn bộ archive vào prompt. Hệ thống tạo handoff event, retrieve contract cùng interface và đúng scope, sau đó gọi verifier.

Nếu verifier pass, workflow tiếp tục. Nếu verifier fail, contract cung cấp owner và recovery route. Trong synthetic join workflow, artifact được trả về planner và planner hoàn thiện cardinality. Trong GSM8K, planner nhận invalid JSON artifact, danh sách violation và executable contract schema, sau đó được yêu cầu repair artifact trước khi solver chạy.

Sham retry dùng cùng public check để quyết định có chi thêm call hay không nhưng không cung cấp required field và recovery guidance của learned contract. Static verifier dùng cùng executable check nhưng được viết sẵn và không mang evidence về extraction hoặc admission. Hai control này lần lượt tách retry compute effect và verifier availability effect.

# 8 Contract bank và quản trị vòng đời

## 8.1 Retrieval

Current synthetic retrieval thực hiện ba filter cứng:

- Contract phải có status admitted.
- Interface phải khớp handoff.
- Scope guard phải trả về true.

Sau đó contract được rank theo conditional benefit và size. Đây chưa phải semantic retrieval trên open domain; nó phù hợp với typed interface retrieval trong pilot hiện tại.

## 8.2 Admission

Admission dùng downstream evidence thay vì chỉ tin extractor. Replay gain, harmful flips, transfer success và veto accuracy đều tham gia decision. Đây là phần gần nhất với novelty nucleus hiện tại: executable contract chỉ được trở thành memory sau khi downstream contribution và boundary behavior được kiểm tra.

## 8.3 Eviction

Khi tổng storage proxy vượt budget, bank xếp contract theo conditional benefit và footprint rồi giữ tập contract phù hợp ngân sách. Implementation hiện thay contract trùng `contract_id` bằng version mới, nhưng chưa có explicit version lineage, merge hoặc conflict resolution.

## 8.4 Thành phần chưa có

Current bank chưa triển khai learned relevance model, uncertainty calibrated utility, contract consolidation, revision under concept drift, online prequential evaluation hoặc provenance graph ở cấp task và seed.

# 9 Protocol synthetic

## 9.1 Task domain

Synthetic task là data transformation join với public statistics và declared intent. Mỗi task cung cấp left row count, actual cardinality, expected rows, join keys và intent. `expected_rows` được coi là public declared data contract trong toy domain, không phải hidden evaluator answer.

Mỗi template group gồm one to one, one to many và many to one variants. Audit và final split thêm intentional many to many expansion làm boundary case.

## 9.2 Split

| Split | Template groups | Task mỗi group | Boundary |
|---|---:|---:|---|
| Build | 10 | 3 | Không |
| Dev | 5 | 3 | Không |
| Audit | 3 | 4 | Có |
| Final | 8 | 4 | Có |

Group id chứa tên split, vì vậy template groups disjoint giữa build, dev, audit và final.

## 9.3 Role profiles

Source profile có planner omission rate 0.62, solver ignore plan rate 0.03 và reviewer detection rate 0.65. Transfer profile giữ planner omission rate 0.62 nhưng tăng solver ignore plan rate lên 0.10 và giảm reviewer detection rate xuống 0.45.

Text rule, success memory và contrastive patch được mô phỏng bằng compliance coefficients. Contract check khác các textual arms ở chỗ verifier trực tiếp quan sát typed artifact và recovery được route về owner.

## 9.4 Experimental arms

| Arm | Intervention |
|---|---|
| No memory | Chạy fixed workflow không thêm memory |
| Text rule | Giảm xác suất omission theo compliance của textual instruction |
| Sham retry | Kiểm tra violation và retry planner nhưng không cung cấp contract guidance |
| Static verifier | Dùng verifier viết sẵn, không học và không admission |
| Contract check | Retrieve admitted contract, verify và route recovery |

## 9.5 Statistical protocol

Các arm được matched bằng deterministic per decision draw. Final success delta dùng cluster bootstrap theo template group thay vì coi từng variant trong cùng group là độc lập.

# 10 Protocol tiny experiment

Tiny experiment là sanity check ba arm trên sáu task từ hai held out final groups. Success only memory được hình thành bằng cách quan sát những field nào có giá trị trong successful build plan. Hàm này không đọc plan của failure trajectory.

Ba arm là no memory, success only memory và contract check. Claim nội bộ của script được support khi contract success rate đồng thời cao hơn hai baseline. Đây là smoke test cơ chế, không phải external validity evidence.

# 11 Protocol GSM8K với model thật

## 11.1 Data và sampling

Code tải GSM8K train và test từ repository công khai. Gold answer được parse bằng `Decimal`. Build và evaluation dùng answer blind longest question stress slice: task được chọn theo độ dài câu hỏi, không nhìn answer, sau đó trả về dataset order.

Sampling này cố ý tạo stress test có thể tái lập, nhưng không đại diện cho toàn GSM8K. Các artifact 10 task qua nhiều seed vẫn dùng cùng một test slice.

## 11.2 Agent workflow

Planner được yêu cầu trả JSON với ba field:

- `operations`: danh sách bước tính ngắn.
- `answer_unit`: đơn vị đáp án.
- `check`: kiểm tra độc lập.

Solver nhận question và planning artifact, sau đó trả `FINAL_ANSWER`. Real workflow hiện gồm planner và solver; reviewer role không được gọi.

## 11.3 Real contract

Verifier kiểm tra field tồn tại, không rỗng và `operations` là list string. Nếu contract đã admitted và plan vi phạm schema, planner nhận violation list cùng contract rồi được gọi lại để repair.

Admission hiện chỉ yêu cầu cumulative evidence có ít nhất một failure với observable schema violation và ít nhất một successful valid handoff. Không có counterfactual replay, harm gate, transfer gate hoặc boundary veto trước admission trong real pipeline.

## 11.4 Arms

| Arm | Cách chạy |
|---|---|
| No memory | Planner và solver, không memory |
| Success only memory | Chèn full plan artifact từ successful build run vào planner prompt |
| CoProMem | Chạy schema verifier và repair call nếu contract admitted và plan invalid |

## 11.5 Cost control

OpenRouter client kiểm tra maximum successful calls và accumulated USD trước mỗi request. Usage report lưu prompt, completion, cached và reasoning tokens, latency và provider model. Retry hiện hỗ trợ HTTP 429, 502, 503 và 504 với tối đa ba attempt. Transport errors và malformed successful responses chưa có recovery tương đương.

# 12 Literature baseline adapters

Current benchmark script đưa ba research baselines vào chung GSM8K harness.

## 12.1 ExpeL adapter

Build trajectories gồm question, planner artifact, prediction và outcome được đưa vào một induction call. Model được yêu cầu contrast success và failure để tạo tối đa bốn general high level rules. Rule được inject vào planner khi evaluation.

Đây là adaptation của insight extraction control flow, không phải exact reproduction trên original ExpeL task suite.

## 12.2 Agent Workflow Memory adapter

Chỉ successful build trajectories được ưu tiên để induction reusable workflow. Các giá trị instance specific được yêu cầu abstract. Workflow text được inject vào planner của evaluation task.

Đây là adaptation của offline workflow induction, với build set nhỏ hơn published system.

## 12.3 CRITIC adapter

CRITIC arm yêu cầu model viết arithmetic Python program, chạy program bằng restricted AST interpreter, đưa execution report vào critique call, rồi gọi correction. Interpreter chỉ cho phép straight line single target assignments, arithmetic operators và một tập function an toàn. Nếu correction không execute nhưng initial program execute được, reconciled evaluator giữ initial prediction.

CRITIC dùng ba calls mỗi task, trong khi memory planning arms thường dùng hai calls và CoProMem dùng thêm repair call khi activated.

## 12.4 Provenance hiện tại

Artifact đã ghi các revision:

- ExpeL `e41ec9a24823e7b560c561ab191441b56d9bcefc`.
- Agent Workflow Memory `8c0ff8cd11d648c8fceb99e4e42f37e3b75381b1`.
- ProphetNet CRITIC `5cf70eb41cdaa1d8faa3e1265d95ee5792d49a53`.

Ba path trong `vendor` hiện được commit dưới dạng gitlink nhưng repository không có `.gitmodules`; working directories hiện rỗng. Do đó source baseline không thể tự động restore từ checkout hiện tại. Hàm revision lookup cũng có thể đi ngược lên parent repository và ghi nhầm CoProCon commit nếu vendor directory rỗng.

# 13 Metrics và nguyên tắc đánh giá

## 13.1 Task metrics

- Success rate hoặc pass at 1.
- Macro success theo template group trong synthetic.
- Downstream error rate.
- Exact numeric match trên GSM8K.
- Answer parse rate.

## 13.2 Mechanism metrics

- Initial và final artifact schema pass rate.
- Recovery activation rate.
- Recovery verifier pass rate.
- Recovered task success rate.
- In scope coverage.
- Transfer success.
- Veto accuracy.
- Boundary harmful flips.

## 13.3 Paired metrics

- Beneficial flips.
- Harmful flips.
- Net gain.
- Clustered bootstrap success delta theo template group trong synthetic.

## 13.4 Efficiency metrics

- Agent calls và calls per task.
- Total tokens và tokens per task.
- Successful tasks per 1000 tokens.
- Mean, p50 và p95 latency.
- Total USD, USD per task và USD per success.
- Verifier cost và injected contract token proxy.
- Lifecycle construction cost trong synthetic.

## 13.5 Attribution requirement

Để paired metric có causal interpretation, các arm phải dùng cùng task, cùng initial artifact hoặc cùng deterministic draw, cùng model version, seed, decoding và tool state. Chỉ checkpoint intervention được phép khác. Synthetic đáp ứng điều kiện này bằng deterministic per decision draw. Real GSM8K hiện gọi provider độc lập cho từng arm; provider có thể nondeterministic ngay cả khi temperature bằng 0 và request seed giống nhau.

# 14 Kết quả thực nghiệm hiện có

## 14.1 Full synthetic final set

Final set gồm 32 task từ tám template groups.

| Arm | Success rate | Downstream error | Runtime cost mỗi task | Verifier cost mỗi task |
|---|---:|---:|---:|---:|
| No memory | 40.6% | 59.4% | 3.000 | 0.0000 |
| Sham retry | 53.1% | 46.9% | 3.444 | 0.0375 |
| Text rule | 68.8% | 31.3% | 3.000 | 0.0000 |
| Static verifier | 81.3% | 18.8% | 3.444 | 0.0375 |
| Contract check | 81.3% | 18.8% | 3.444 | 0.0375 |

Contract check so với no memory tạo 13 beneficial flips, 0 harmful flips và net gain 13.

Replay trước minimization trên 30 build checkpoints đạt contract success 100%, no memory 26.7%, sham retry 50.0% và text rule 60.0%. Replay sau minimization trên 15 dev checkpoints đạt contract success 93.3%, no memory 46.7%, sham retry 53.3% và text rule 66.7%. Contract giữ lại `declared_cardinality` và bỏ `expected_rows` khỏi required fields.

Scope evaluation đạt in scope coverage 100%, in scope success 80%, transfer success 80%, boundary harmful flips 0 và veto accuracy 100%. Một contract được admit.

## 14.2 Tiny synthetic experiment

Tiny experiment gồm sáu preserve rows task từ hai held out groups.

| Arm | Success rate | Paired harmful flips so với CoProCon |
|---|---:|---:|
| No memory | 50.0% | 0 |
| Success only memory | 66.7% | 0 |
| Contract check | 100.0% | Không áp dụng |

Script đánh dấu central claim được support trong run này. Kết luận chỉ áp dụng cho synthetic mechanism check.

## 14.3 Real GSM8K micro runs

Các artifact hiện có cho thấy sensitivity cao theo model, seed và admission state.

| Run | Model | Eval tasks | No memory | Success only | CoProMem | Contract admitted |
|---|---|---:|---:|---:|---:|---|
| Micro | Ministral 3B | 4 | 75% | 50% | 25% | Có |
| Micro | DeepSeek V4 Flash | 4 | 50% | 75% | 50% | Không |
| Ten task | DeepSeek V4 Flash | 10 | 80% | 70% | 90% | Có |
| Seed 17 | DeepSeek V4 Flash | 10 | 70% | 80% | 70% | Không |
| Seed 17 cumulative | DeepSeek V4 Flash | 10 | 70% | 60% | 70% | Có |
| Seed 23 cumulative | DeepSeek V4 Flash | 10 | 70% | 70% | 70% | Có |
| Seed 41 cumulative | DeepSeek V4 Flash | 10 | 70% | 80% | 80% | Có |
| Seed 73 cumulative | DeepSeek V4 Flash | 10 | 70% | 80% | 80% | Có |

Trên bốn cumulative seeded runs, pooled descriptive rates là no memory 70.0%, success only 72.5% và CoProMem 75.0%. Paired CoProMem versus no memory có 3 beneficial flips, 1 harmful flip và net gain 2 trên 40 task runs.

Tuy nhiên, hai beneficial flips ở seed 41 và 73 xảy ra khi `recovered = false`; CoProMem không thực hiện contract intervention. Chúng không thể được quy trực tiếp cho recovery. Ở seed 23, hai task có outcome khác nhau đều activated recovery nhưng gồm một beneficial và một harmful flip, net bằng 0. Vì vậy pooled plus 5 percentage points chưa phải causal evidence cho CoProCon.

## 14.4 Literature style comparison

Reconciled 20 task stress slice với DeepSeek V4 Flash cho kết quả:

| Arm | Correct | Accuracy | Calls | Tokens | USD |
|---|---:|---:|---:|---:|---:|
| ExpeL | 14 trên 20 | 70% | 40 | 16684 | 0.00209 |
| Agent Workflow Memory | 17 trên 20 | 85% | 40 | 20431 | 0.00243 |
| CRITIC | 17 trên 20 | 85% | 60 | 29073 | 0.00430 |
| CoProMem | 16 trên 20 | 80% | 48 | 20495 | 0.00260 |

ExpeL induction trả provider null content trong initial run và reconciled report đánh dấu arm này là excluded. Giá trị 70% không phải valid ExpeL memory result.

CoProMem thấp hơn Agent Workflow Memory và reconciled CRITIC một task. So paired, CoProMem có net minus 1 so với mỗi phương pháp này. Literature script không có no memory và success only arm, nên không xác định được CoProMem 80% có cao hơn fixed workflow cơ bản trên cùng run hay không.

# 15 Diễn giải khoa học

## 15.1 Điều đã được hỗ trợ

Implementation hỗ trợ mạnh claim rằng executable verifier tại handoff có thể ngăn một lớp coordination error trong môi trường có typed artifact và observable invariant. Recovery routing về owner hiệu quả hơn blind retry trong synthetic domain. Scope guard có thể veto declared boundary condition. Contract bank có thể lưu contract và evidence dưới dạng inspectable, budgeted object.

Synthetic results cũng cho thấy textual rule không đạt cùng mức với executable check trong simulator hiện tại. Đây là bằng chứng cơ chế hữu ích để biện minh cho việc nghiên cứu memory dưới dạng contract thay vì chỉ prompt text.

## 15.2 Điều chưa được hỗ trợ

Static verifier và learned contract có cùng success rate 81.3%. Do đó chưa có evidence rằng trajectory derived learning tạo thêm giá trị so với một verifier viết sẵn.

Real GSM8K contract không được synthesize từ procedural difference. Schema, required fields và recovery route được định nghĩa trước. Admission không dùng counterfactual replay hoặc harm gate. Vì vậy real experiment hiện là schema repair pilot, chưa phải complete CoProCon idea validation.

Directional gains trong cumulative GSM8K runs bị trộn với provider nondeterminism vì các arm gọi planner và solver riêng. Hai trong ba beneficial flips không có contract activation. Không thể coi plus 5 percentage points là causal gain.

Literature comparison chưa đủ baseline breadth, thiếu no memory control và không phải exact reproduction. CoProMem cũng chưa vượt hai baseline mạnh nhất trên 20 task stress slice.

## 15.3 Novelty nucleus hiện tại

Novelty candidate hợp lý nhất là:

> CoProCon derives scoped procedural contracts from matched successful and failed handoffs, validates their counterfactual downstream contribution and boundary harm before admission, then executes their verifier and owner specific recovery route at future handoffs under read, storage and verification budgets.

Current synthetic implementation gần với câu này. Current real implementation chưa thực hiện đầy đủ phần derives from matched handoffs, counterfactual validation và boundary harm before admission.

# 16 Threats to validity

## 16.1 Construct validity

Synthetic task được thiết kế đúng với verifier nên effect có thể là built in. `force_complete = true` đảm bảo planner sửa artifact khi contract kích hoạt. Role profile rates và textual compliance là tham số simulator, không phải behavior đo từ model thật.

GSM8K schema completeness chỉ là proxy yếu cho procedural correctness. Một plan đầy đủ nhưng sai vẫn pass verifier. Ngược lại, model có thể giải đúng dù plan thiếu field.

## 16.2 Internal validity

Real arms không tái sử dụng cùng initial planner artifact. Separate provider calls có thể khác nhau dù temperature zero. Paired flips vì vậy trộn intervention effect và sampling variation.

Cumulative evidence không lưu unique provenance và không chống duplicate report. Cùng task, seed hoặc report có thể bị cộng nhiều lần.

Success only memory inject full plan của một source instance, bao gồm operations và numeric details. Điều này có thể tạo irrelevant context hoặc instance leakage, dù prompt yêu cầu chỉ dùng format và pattern.

## 16.3 Statistical conclusion validity

Real runs chỉ có bốn hoặc mười task; literature comparison có hai mươi task. Không có confidence interval hoặc hierarchical aggregation cho real reports. Các run qua seed dùng cùng test items nên không được coi là bốn mươi independent tasks.

Synthetic cluster bootstrap chỉ có tám final groups. Nó phù hợp cho regression test nhưng vẫn quá nhỏ cho broad empirical claim.

## 16.4 External validity

Synthetic join workflow không đại diện cho open ended tool use hoặc heterogeneous MAS. GSM8K có thể nằm trong pretraining data và không có repeated procedural family metadata. Longest question stress slice không đại diện cho dataset distribution.

Hiện mới có một external benchmark. Chưa có code repair, repeated tool workflow, document synthesis hoặc collaborative planning benchmark.

## 16.5 Baseline validity

ExpeL và AWM là prompt and control flow adaptations, không phải exact runs của author repositories trên original tasks. CRITIC dùng restricted interpreter và một correction iteration. Compute budgets khác nhau giữa arms. Vendor source hiện không restore được từ repository do thiếu `.gitmodules`.

## 16.6 Reproducibility validity

Synthetic experiments hoàn toàn reproducible bằng standard library. Real reports phụ thuộc OpenRouter provider, model routing và potential nondeterminism. Artifact lưu provider model IDs và usage nhưng chưa lưu prompt hash, response raw text cho mọi call, request ID hoặc endpoint metadata đầy đủ.

# 17 Mức độ hoàn thành của implementation

| Thành phần | Synthetic | Real GSM8K | Trạng thái research |
|---|---|---|---|
| Typed handoff artifact | Có | Có | Hoàn thành cơ bản |
| Observable trace | Có | Có một phần | Cần raw call provenance |
| Success failure pairing | Theo group | Chỉ đếm aggregate | Chưa hoàn thành real |
| Divergence localization | Missing cardinality | Schema violation | Hẹp |
| Learned contract extraction | Deterministic domain rule | Không | Chưa hoàn thành real |
| Executable verifier | Có | Có | Hoàn thành cơ bản |
| Owner recovery routing | Có | Có | Hoàn thành cơ bản |
| Scope guard | Có | Không | Chưa hoàn thành real |
| Counterexample veto | Qua intent guard | Không | Cần semantic construction |
| Matched replay | Có | Không | Cần sửa real protocol |
| Clause minimization | Có | Không | Cần real validation |
| Utility aware admission | Có | Không | Cần port sang real |
| Budgeted retrieval | Có | Universal contract | Chưa multi contract real |
| Eviction | Có | Không | Pilot only |
| Consolidation revision | Không | Aggregate counts | Chưa có |
| Executor transfer | Synthetic profile swap | Nhiều run riêng | Chưa controlled |
| Canonical benchmark adapter | Không | GSM8K coupled | Chưa có |
| Literature baselines | Controls | Ba adapters | Chưa đủ 5 đến 6 |

Code hiện có 12 automated tests. Tất cả pass và toàn bộ source compile thành công. Static checker báo 36 vấn đề auto fixable, chủ yếu import order, unused imports và typing style. Test coverage còn thiếu các edge case của retrieval, eviction, admission failure, evidence deduplication, task alignment, OpenRouter transport error và full literature benchmark.

# 18 Acceptance criteria cho idea validation

CoProCon chỉ nên được coi là pass Step 1 khi thỏa các điều kiện sau.

## 18.1 Contract formation

- Contract được tạo từ ít nhất một matched success failure pair có cùng task hoặc procedural family.
- Extractor output gồm interface, condition, verifier, owner, recovery và scope.
- Không dùng hidden evaluator answer hoặc future test data.
- Evidence lưu source task IDs, model, seed, prompt hash và extractor version.

## 18.2 Causal checkpoint validation

- Các arm dùng chung initial artifact hoặc exact checkpoint snapshot.
- No memory và contract arm chỉ khác intervention.
- Seed, model, decoding, tool state và call budget được matched.
- Contract tạo positive net gain và harm không vượt declared cap.

## 18.3 Transfer

- Source task và evaluation task khác instance.
- Transfer được đo trên unseen task cùng procedural family.
- Có boundary task và out of scope task.
- Bank không rỗng và contract thật sự được retrieve hoặc activated.

## 18.4 Baseline comparison

Core POC tối thiểu phải có no memory, success only memory, textual reflection hoặc rule, static verifier, sham retry và CoProCon. CoProCon cần tốt hơn no memory và ít nhất một memory baseline đơn giản; learned contract value phải được tách khỏi static verifier value.

## 18.5 Stability

Directional improvement phải xuất hiện trên nhiều source groups và không chỉ do một task hoặc provider draw. Report phải tách activated subgroup, non activated subgroup và all task aggregate.

# 19 Kế hoạch nghiên cứu tiếp theo

## 19.1 Giai đoạn A hoàn thiện real core POC

1. Tách planner generation khỏi arm execution và lưu immutable checkpoint.
2. Cho mọi arm tiếp tục từ cùng planning artifact.
3. Thu nhiều rollout trên build tasks để có matched valid invalid handoffs.
4. Thêm typed extractor tạo contract proposal từ contrast thay vì hard code schema.
5. Replay candidate trên held out checkpoints trước admission.
6. Thêm static verifier và sham retry vào real experiment.
7. Port scope, boundary, minimization và utility admission từ synthetic sang real pipeline.
8. Báo riêng effect khi contract activated và khi không activated.

## 19.2 Giai đoạn B novelty audit

Literature audit cần đối chiếu success failure contrast, process supervision, workflow memory, executable guardrails, runtime verification, program repair, agent reflection, causal memory admission, scope guards và lifelong memory management. Mỗi prior work cần paper, official code, stored unit, extraction mechanism, retrieval mechanism, validation protocol và overlap với CoProCon.

## 19.3 Giai đoạn C benchmark và baseline selection

Chọn bốn benchmark có repeated procedural structure và observable handoff artifact. Candidate families gồm repeated tool use, code repair, document synthesis và collaborative planning. Mỗi benchmark phải có canonical adapter, deterministic scorer khi có thể, task family metadata và boundary cases.

Baseline suite mục tiêu gồm no memory, raw episodic memory, success only memory, reflection or insight memory, workflow memory, static verifier và một strong recent memory agent. Literature baseline không nên chỉ là nhiều biến thể vector similarity retrieval.

## 19.4 Giai đoạn D canonical adapter

Shared interface nên bao gồm:

```text
load split
reset task
observe public state
execute role action
emit typed artifact
checkpoint handoff
resume with intervention
score episode
return task family and boundary metadata
```

CoProCon và mọi baseline phải dùng cùng adapter, task state, scorer và episode budget. Method specific logic chỉ nằm phía trên canonical episode interface.

## 19.5 Giai đoạn E subset pilot

Sau khi reproduction pass, chọn một benchmark và một subset nhỏ. Chạy toàn bộ baseline với shared tasks, seeds và budgets. Pilot chỉ quyết định signal, fairness, stability và cost; không dùng để đưa publication scale claim.

# 20 Ngôn ngữ claim được phép sử dụng

## 20.1 Claim hiện được phép

- CoProCon implements typed executable contracts at agent handoffs.
- The synthetic pilot demonstrates end to end feasibility of verification, recovery routing, scope veto, admission and budgeted persistence.
- In the synthetic join simulator, executable checking outperforms no memory, blind retry and textual rules without observed harmful flips.
- Real GSM8K experiments demonstrate that schema triggered recovery can be executed and measured under a bounded API budget.
- Current real results are descriptive and inconclusive regarding causal task improvement.

## 20.2 Claim chưa được phép

- CoProCon is proven to outperform state of the art memory agents.
- Contrast derived contracts improve GSM8K accuracy.
- Learned contracts outperform hand written verifiers.
- The method generalizes across benchmarks or agent architectures.
- Current literature adapters constitute exact reproduction of ExpeL, AWM or CRITIC.
- The pooled plus 5 percentage point GSM8K difference is caused by CoProCon.

# 21 Reproducibility và artifact inventory

## 21.1 Environment

- Python từ 3.10 trở lên.
- Không có required third party runtime dependency.
- Real experiments cần `OPENROUTER_API_KEY` trong `.env`.
- Package entry points được khai báo trong `pyproject.toml`.

## 21.2 Commands

```text
python -m pip install -e .
python -m pytest
python -m copromem.experiment --seed 7 --output artifacts/synthetic_report.json
python -m copromem.tiny_experiment --seed 7 --output artifacts/tiny_experiment.json
python -m copromem.real_gsm8k_experiment --output artifacts/gsm8k_real_micro.json
python -m copromem.literature_baselines_experiment --seed 42 --output artifacts/gsm8k_literature_seed42_20test.json
```

## 21.3 Artifact chính

- `synthetic_report.json`: full synthetic result.
- `synthetic_report_run_20260915.json`: repeated synthetic run.
- `tiny_experiment_run_20260915.json`: tiny three arm result.
- `gsm8k_real_micro_20260915.json`: Ministral micro run.
- `gsm8k_real_micro_deepseek_v4_flash_20260915.json`: DeepSeek micro run.
- `gsm8k_real_10test_deepseek_v4_flash_20260915.json`: ten task run.
- Các file `seed17`, `seed23`, `seed41`, `seed73` cumulative: repeated provider seed runs.
- `gsm8k_literature_seed42_20test_20260915.json`: initial literature adapter run.
- `gsm8k_literature_seed42_20test_20260915_reconciled.json`: report sau CRITIC carry forward reconciliation và ExpeL validity annotation.

## 21.4 Current repository status

Source of truth hiện tại là commit `ad53523`. Test suite có 12 test và pass toàn bộ tại thời điểm lập tài liệu. Synthetic experiment seed 7 tái tạo no memory 40.6%, contract check 81.3% và 13 beneficial, 0 harmful flips. Tiny experiment tái tạo no memory 50.0%, success only 66.7% và contract check 100.0%.

## 21.5 Quyết định nghiên cứu tại thời điểm hiện tại

CoProCon đã vượt qua engineering feasibility và synthetic mechanism gate. Nó chưa vượt qua real idea validation gate. Công việc tiếp theo không phải scale số benchmark ngay, mà là sửa real checkpoint experiment để learned contract formation và causal intervention được kiểm tra đúng. Sau khi gate này pass, novelty audit, baseline reproduction, canonical adapters và subset comparison mới tạo được evidence đủ sạch cho quyết định paper direction.
