# Ghi chú đã kiểm chứng: thiết lập thực nghiệm các paper memory/decomposition

**Ngày kiểm tra:** 19-09-2026.  
**Phạm vi:** đọc paper gốc/official proceedings ở các URL được yêu cầu, ưu tiên phần *Experimental Setup* và appendix. Các con số dưới đây không được suy diễn từ bảng tổng hợp cũ.

## Tóm tắt chuẩn hoá

| Paper | Benchmark / subset thực sự được chạy | Model chính | Metric / protocol đáng chú ý |
|---|---|---|---|
| ReasoningBank | WebArena: 684 task (bỏ Maps); Mind2Web: cross-task/cross-website/cross-domain; SWE-Bench-Verified: 500 instance | Gemini-2.5-Flash, Gemini-2.5-Pro, Claude-3.7-Sonnet | SR + average steps; WebArena BrowserGym/ReAct, tối đa 30 bước; SWE theo mini-SWE-Agent bash-only |
| ReMe | BFCL-V3: 50 base multi-turn để tạo memory + 150 eval; AppWorld: 90 train + 168 `test_normal` | Qwen3-8B, Qwen3-14B, Qwen3-32B; thêm 6 backbone ở generalization | Avg@4 và Pass@4, 3 independent runs; baseline No Memory, A-Mem, LangMem |
| Search2Skill | SuperGPQA: Math/Management/Science; MMLU-Pro: Law/Philosophy/History; held-out thêm EvoAgentBench OmniMath/LiveCodeBench | RL collector 8B; transfer executor Qwen3-4B/14B; Qwen3-30B-A3B làm judge/compressor | Accuracy; streaming vs held-out 2:1 collection:test; LCB 97 collect/39 test, lặp test 3 lần |
| LEGOMem | OfficeBench duy nhất: 300 = 148 memory-curation train + 152 test; Level 1/2/3 | GPT-4o team; hybrid GPT-4o + GPT-4o-mini; mini-only GPT-4o-mini | Programmatic SR; 3 seeds; 93 successful full-task memories và 250 subtask memories |
| AWM | WebArena: 812 tasks, online; Mind2Web: offline và online, cross-task/cross-website/cross-domain | GPT-4-0613 (WebArena); GPT-3.5-turbo và GPT-4 (Mind2Web) | SR, steps; WebArena online-only; Mind2Web element accuracy, action F1, step SR, task SR |
| ExpeL | HotpotQA, ALFWorld, WebShop, FEVER | gpt-3.5-turbo-0613 hành động; ablation dùng GPT-4 để extract insight | 4-fold validation (mean ± SE); success rate; WebShop reward bổ sung |
| Reflexion | ALFWorld 134 task/6 loại; HotpotQA 100 câu; HumanEval, MBPP, LeetcodeHardGym 40 câu; HumanEval/MBPP Rust subset 50 hard | text-davinci-003, gpt-3.5-turbo, GPT-4; Starchat-beta analysis | ALFWorld retries + memory tối đa 3 reflection; HotpotQA exact match; code pass@1 |
| Synapse | MiniWoB++ 48 task được chọn, 50 episode/task; Mind2Web train memory + Cross-Task/Cross-Website/Cross-Domain tests | gpt-3.5-turbo-0301 (MiniWoB++); gpt-3.5-turbo-16k-0613 và CodeLlama-7B (Mind2Web) | MiniWoB SR; Mind2Web element accuracy, step SR, task SR; `text-embedding-ada-002` + FAISS |
| ADaPT | ALFWorld 134 unseen test, 10 seen-dev/task; WebShop 100/500 test query + 40 dev; TextCraft 200 test (77 d2, 123 d3, 11 d4) | text-davinci-003 (ALFWorld), gpt-3.5-turbo (WebShop), gpt-3.5-turbo-instruct (TextCraft); LLaMA-2-70B/Lemur-70B analysis | Task SR; budgets 20/15/20 environment iterations; depth 3/3/4 |
| Demystify Memory in MLE Agents | MLE-Bench Lite: 22 task được tuyển từ MLE-Bench 75 Kaggle task | AIDE + o3 (tree); OpenHands + GPT-4o (chain); MLAB + GPT-4o estimated/rebuttal | 24h/task; AIDE 16 seeds, OpenHands 3; medals, above-median, made/valid submission, best metric, bugs/diversity |

## Ghi chú theo từng paper

### 1. ReasoningBank — [arXiv:2509.25140](https://arxiv.org/abs/2509.25140)

- **Benchmark:** WebArena, Mind2Web và SWE-Bench-Verified — **không phải** VisualWebArena, AgentBench hoặc SWE-bench Lite.
- **Subset/split:** WebArena loại Maps vì lỗi website; năm split còn lại Shopping 187, Admin 182, GitLab 180, Reddit 106, Multi 29, tổng **684**. SWE-Bench-Verified có **500** instance đã được verified thủ công.
- **Model/harness:** Gemini-2.5-Flash, Gemini-2.5-Pro, Claude-3.7-Sonnet. Web dùng BrowserGym + ReAct, tối đa 30 bước, temperature 0.7. SWE theo mini-SWE-Agent, bash-only, ReAct, không scaffold/tool đặc biệt.
- **So sánh:** No Memory, Synapse, AWM. Metric WebArena: SR/average steps; SWE: resolve rate/average steps. Không có GPT-4o hay Llama-3.1-70B trong bảng thực nghiệm chính của bản camera-ready v2.

### 2. ReMe — [arXiv:2512.10696](https://arxiv.org/abs/2512.10696) / [ACL Findings 2026](https://aclanthology.org/2026.findings-acl.829/)

- **Benchmark:** BFCL-V3 và AppWorld — **không phải** ALFWorld, WebShop hay ToolBench.
- **Subset/split:** BFCL-V3 lấy ngẫu nhiên **50** task của `base multi-turn` làm initial memory pool, **150** task còn lại để đánh giá. AppWorld: **90 train** để acquire initial experience; **168 `test_normal`** để test.
- **Model:** Qwen3-8B/14B/32B trong bảng chính; generalization thêm sáu model. Thinking mode bị tắt trong thiết lập `ReMe (fixed)` nêu ở ablation.
- **Protocol:** Avg@4 = success trung bình qua 4 trial độc lập; Pass@4 = ít nhất một trial thành công; bảng chính trung bình của 3 runs. Baseline đúng là No Memory, A-Mem, LangMem.

### 3. Search2Skill — [arXiv:2608.05245v1](https://arxiv.org/html/2608.05245v1)

- **Benchmark/domain:** SuperGPQA (Math, Management, Science), MMLU-Pro (Law, Philosophy, History); held-out còn dùng EvoAgentBench: OmniMath và LiveCodeBench. Ba split EvoAgentBench tương tác sandbox bị loại vì nằm ngoài action space.
- **Subset:** SuperGPQA lọc medium/hard rồi sample tối đa 500/domain. Held-out 2:1 collection:test: Math 333/167, Science 333/167, Philosophy 333/167; Law 248/124; History 254/127. OmniMath 478/100; LiveCodeBench 97/39 (test chạy 3 lần).
- **Model/protocol:** collector RL 8B; library transfer sang executor Qwen3-4B và Qwen3-14B. Qwen3-30B-A3B dùng để nén trang và judge OmniMath. Temperature 0.3, thinking bật, tối đa 15 round và 5 web searches.
- **Metric:** accuracy; MCQ exact option match, OmniMath LLM judge, LiveCodeBench chạy unit test. Đây là paper về expert QA/skill + web search, không phải benchmark computer-control hay workflow stateful.

### 4. LEGOMem — [ACM DOI](https://dl.acm.org/doi/10.65109/VLUA1303) / [arXiv:2510.04851](https://arxiv.org/abs/2510.04851)

- ACM landing page không trả nội dung qua crawler; thông tin được đối chiếu bằng bản AAMAS/arXiv của chính paper.
- **Benchmark:** chỉ **OfficeBench**, không có GAIA. 300 task được split **148 train** (curation) và **152 test** (evaluation); Level 1 single-app, Level 2 two-app, Level 3 multi-app.
- **Model/team:** full LLM = GPT-4o cho orchestrator và task agent; hybrid = GPT-4o orchestrator + GPT-4o-mini task agent; SLM = GPT-4o-mini toàn team. Retriever `text-embedding-3-large` + FAISS; OCR `Phi-3.5-mini`.
- **Memory/test:** từ 148 train task, giữ 93 success trajectory làm full-task memory, trích 250 subtask memory. So sánh No memory, Synapse (adapted), AWM (adapted); top-5 memory cho orchestrator và top-3/task-agent; SR theo final environment state, 3 random seeds.

### 5. AWM — [arXiv:2409.07429](https://arxiv.org/abs/2409.07429)

- **Benchmark:** WebArena và Mind2Web, không có ALFWorld/WebShop.
- **WebArena:** toàn bộ 812 task trên 5 website; GPT-4 `gpt-4-0613`, temperature 0, BrowserGym. Vì chỉ có test example nên chỉ đánh giá AWM **online/streaming**, theo website; metric SR và steps.
- **Mind2Web:** AWM offline và online, GPT-3.5-turbo lẫn GPT-4; kết quả theo Cross-Task, Cross-Website, Cross-Domain; metric element accuracy, action F1, step SR, task SR.

### 6. ExpeL — [arXiv:2308.10144](https://arxiv.org/abs/2308.10144)

- **Benchmark:** HotpotQA, ALFWorld, WebShop, FEVER; FEVER được thêm riêng để test cross-domain transfer với HotpotQA.
- **Protocol/model:** tất cả dùng four-fold validation, báo mean + standard error. Agent action là `gpt-3.5-turbo-0613`, temperature 0/greedy; GPT-4 xuất hiện ở ablation model dùng để extract insight.
- **Metric/baseline:** success rate (exact match HotpotQA/FEVER; complete-in-time ALFWorld; mua đúng mọi thuộc tính WebShop); thêm mean reward của WebShop. Baseline chính ReAct và Act; IL lấy từ paper ReAct.

### 7. Reflexion — [arXiv:2303.11366](https://arxiv.org/abs/2303.11366)

- **Benchmark:** ALFWorld (134 environment, 6 task type), HotpotQA (100 câu trong thí nghiệm), HumanEval, MBPP, và LeetcodeHardGym (40 LeetCode hard sau cutoff GPT-4). Rust: 50 HumanEval hard problem và các subset MBPP được dịch qua MultiPL-E.
- **Model:** text-davinci-003, gpt-3.5-turbo, GPT-4; có analysis Starchat-beta. Do đó không nên gán duy nhất GPT-4 hoặc quy đổi kết quả qua model khác.
- **Protocol:** ALFWorld tối đa 30 action/trial, reset khi reflection trigger, giữ tối đa 3 reflection; HotpotQA exact match/2-shot ReAct (CoT 6-shot); code metric pass@1, tối đa 6 self-generated unit test và memory tối đa 1 experience.

### 8. Synapse — [arXiv:2306.07863](https://arxiv.org/abs/2306.07863)

- **Benchmark:** MiniWoB++ và Mind2Web — không có WebArena trong paper này.
- **Subset/model:** MiniWoB++ dùng 48 task được chọn, 50 episode/task, `gpt-3.5-turbo-0301`. Mind2Web dùng `gpt-3.5-turbo-16k-0613` mặc định và CodeLlama-7B comparison; train trajectory được lưu vào memory, test là Cross-Task/Cross-Website/Cross-Domain.
- **Protocol:** temperature 0; `text-embedding-ada-002` và FAISS; top exemplar retrieval. Metrics Mind2Web gồm element accuracy, step SR, task SR.

### 9. ADaPT — [arXiv:2311.05772](https://arxiv.org/abs/2311.05772)

- **Benchmark:** ALFWorld, WebShop, TextCraft — không có WebArena, StrategyQA.
- **Subset:** ALFWorld 134 unseen test, dev = 10 seen game/task. WebShop dùng 100 user instruction trong 500 test query; dev riêng 40 query. TextCraft test 200 (77 depth-2, 123 depth-3, 11 depth-4).
- **Model/budget:** `text-davinci-003` ALFWorld, `gpt-3.5-turbo` WebShop, `gpt-3.5-turbo-instruct` TextCraft; analysis LLaMA-2-70B và Lemur-70B. Environment budget 20/15/20 iterations; max decomposition depth 3/3/4.
- **Metric/baseline:** success rate; ReAct, Plan-and-Execute, Try Again with ReAct, Reflexion, LATS (where reported). WebShop chính thức ưu tiên SR thay vì soft reward.

### 10. Demystify the Role of Memory in MLE Agents — [ACL Findings 2026](https://aclanthology.org/2026.findings-acl.525/)

- **Benchmark/subset:** MLE-Bench Lite: **22** task tuyển từ 75 Kaggle task của full MLE-Bench. Paper không dùng một benchmark "Kaggle-style" tự thiết kế riêng.
- **Model/agent:** AIDE với **o3** là tree-search agent; OpenHands với **GPT-4o** là chain agent; MLAB với GPT-4o được ghi `Estimated/Rebuttal` trong Table 1.
- **Protocol:** 24 giờ wall-clock/task; AIDE 16 seeds/task, OpenHands 3 seeds. Metric gồm made/valid submission, above-median, bronze/silver/gold/any-medal, plus best validation metric, bugs và diversity. Đây là nguồn trực tiếp cho kết luận memory có thể tăng reliability nhưng làm hẹp exploration của tree search.

## Hệ quả trực tiếp cho hai tài liệu COPROMEM hiện tại

Các mục sau cần coi là **không được nguồn gốc trong 10 paper này hỗ trợ**, trừ khi có citation/dataset mới độc lập:

1. ReMe chạy ALFWorld/WebShop/ToolBench, ReMe dùng GPT-4o/Llama-3-70B, hoặc ReMe có `18.4% harmful flips` trên Deceptive Twin-Tasks.
2. ReasoningBank chạy VisualWebArena/AgentBench/SWE-bench Lite hay dùng GPT-4o/Llama-3.1-70B trong main table; `31.2% WebArena` không phải số của paper v2 hiện hành.
3. LEGOMem chạy GAIA; paper chỉ báo cáo OfficeBench.
4. Synapse chạy WebArena; paper gốc đánh giá MiniWoB++ và Mind2Web.
5. ADaPT chạy WebArena hay StrategyQA; paper gốc là ALFWorld/WebShop/TextCraft.
6. So sánh trực tiếp với số công bố khi đổi backbone (ví dụ Llama-3.1 → Llama-3.3, GPT-4 Turbo → GPT-4o-mini) không phải controlled replication.

Các điểm trên nên được sửa hoặc gắn nhãn rõ là **hypothesis/target nội bộ**, thay vì literature fact.
