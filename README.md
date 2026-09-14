# CoProMem / CoProCon

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

Thí nghiệm xây bank từ split `build`, tune/minimize trên `dev`, audit boundary trên `audit`, rồi freeze và đánh giá trên `final`. Báo cáo JSON chứa success, paired beneficial/harmful flips, verifier/recovery cost và khoảng tin cậy bootstrap cluster theo template group.

## Synthetic task và giới hạn claim

Task công khai statistics/cardinality của phép join. Planner đôi khi làm mất cardinality trước khi bàn giao; solver sau đó mặc định one-to-one. Contract học được yêu cầu `declared_cardinality`, chạy verifier tại handoff, và đưa artifact về planner để hoàn chỉnh. Với intentional many-to-many expansion, scope guard veto contract để tránh áp dụng nhầm.

Kết quả chỉ là feasibility test tái lập được cho cơ chế CoProCon. Nó không thay cho thử nghiệm với model/agent thật và các dataset nêu trong proposal; report tự ghi rõ giới hạn này.
