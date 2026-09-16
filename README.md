# CoProMem / CoProCon

## Research branch update — 16 September 2026

The current English research record is in [research/README.md](research/README.md).
The original documentation below and in `docs/` is retained as historical context.
No learned-contract performance advantage has been established.

For the full English account, read
[Current code and research evidence](research/009_CURRENT_CODE_RESEARCH_DOCUMENT.md)
and the [proposed research pivot](research/008_PIVOT_RESEARCH_SPECIFICATION.md).

The real GSM8K CLI now requires an explicit configuration and runs the train-only
induction pipeline. The former three-arm commands below are historical, not the
current research protocol. Use `python -m copromem.induction_pilot --help` or the
commands in the research guide. Never develop against the final GSM8K test set.


Implementation tham chiếu cho ý tưởng trong `CoProCon_Research_Proposal.md`:
memory không lưu mẹo theo agent mà lưu **procedural contract có verifier thực thi được** ở điểm bàn giao artifact.

## Nội dung có trong repository

- `src/copromem/types.py`: artifact có kiểu, handoff log, ledger chi phí và metric evidence. Log chỉ giữ state quan sát được; không có chain-of-thought.
- `src/copromem/contracts.py`: schema contract, registry verifier/scope an toàn, counterexample veto và typed extraction từ success/failure divergence.
- `src/copromem/workflow.py`: workflow `planner -> solver -> reviewer`, checkpoint verifier và recovery router được instrument đầy đủ.
- `src/copromem/replay.py`: replay bốn arm matched (`no_memory`, `text_rule`, `sham_retry`, `contract_check`) và minimization bằng clause deletion.
- `src/copromem/synthesis.py` và `src/copromem/bank.py`: localization, proposal, scope/transfer validation, admission, retrieval theo budget, eviction và lưu/đọc contract bank.
- `src/copromem/synthetic.py`: bộ dữ liệu join tự sinh theo source/template group, có boundary case `intentional_expansion` để kiểm thử veto.
- `src/copromem/experiment.py`: thí nghiệm end-to-end, baseline đơn giản, controls và executor-swap transfer.

## Chạy thí nghiệm nhỏ

Không có dependency ngoài standard library.

```bash
python3 -m pip install -e .
python3 -m copromem.experiment --seed 7 --output artifacts/synthetic_report.json
python3 -m pytest
```

## Chạy smoke experiment ba arm

So sánh trực tiếp `no_memory`, memory chỉ học từ trajectory thành công, và
`contract_check` của CoProMem trên 6 task thuộc 2 template group held-out:

```bash
python3 -m copromem.tiny_experiment --seed 7 --output artifacts/tiny_experiment.json
python3 -m pytest tests/test_tiny_experiment.py
```

Đây là smoke test cơ chế synthetic rất nhỏ, không phải bằng chứng tổng quát cho
LLM agent hoặc dataset bên ngoài.

## GSM8K micro-pilot với agent calls thật

Pipeline ba arm dùng OpenRouter qua `OPENROUTER_API_KEY` trong `.env`, mặc định
giới hạn 40 calls và 0.02 USD:

```bash
python3 -m copromem.real_gsm8k_experiment --output artifacts/gsm8k_real_micro.json
python3 -m pytest tests/test_real_gsm8k_experiment.py
```

Thêm `--seed 17` để đổi provider sampling seed mà vẫn giữ nguyên task slice.
Có thể lặp `--prior-report artifacts/previous.json` để tái sử dụng và cộng dồn
evidence success/failure từ các run trước vào contract bank.

Report ghi accuracy/exact match, parse/schema/recovery rate, paired flips,
calls/token/latency trên mỗi task, chi phí tổng/per-task/per-success, cache và
reasoning tokens. Mẫu mặc định chỉ là stress slice 3 build + 4 test nên không
được diễn giải như accuracy đại diện cho toàn GSM8K.

Thí nghiệm xây bank từ split `build`, tune/minimize trên `dev`, audit boundary trên `audit`, rồi freeze và đánh giá trên `final`. Báo cáo JSON chứa success, paired beneficial/harmful flips, verifier/recovery cost và khoảng tin cậy bootstrap cluster theo template group.

## Synthetic task và giới hạn claim

Task công khai statistics/cardinality của phép join. Planner đôi khi làm mất cardinality trước khi bàn giao; solver sau đó mặc định one-to-one. Contract học được yêu cầu `declared_cardinality`, chạy verifier tại handoff, và đưa artifact về planner để hoàn chỉnh. Với intentional many-to-many expansion, scope guard veto contract để tránh áp dụng nhầm.

Kết quả chỉ là feasibility test tái lập được cho cơ chế CoProCon. Nó không thay cho thử nghiệm với model/agent thật và các dataset nêu trong proposal; report tự ghi rõ giới hạn này.
