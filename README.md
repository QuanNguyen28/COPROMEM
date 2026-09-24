# COPROMEM 2.0

COPROMEM nghiên cứu trí nhớ thủ tục có cấu trúc cho agent: phân rã mục tiêu thành các bước/phụ thuộc, truy xuất kinh nghiệm phù hợp, tách các trường hợp dễ bị nhầm, rồi học từ episode để dùng ở nhiệm vụ sau. Đây là mã nghiên cứu và bộ chạy thử nghiệm, không phải một agent production hoặc một kết quả benchmark đã được xác nhận tổng quát. [Tài liệu ý tưởng](docs/COPROMEM_2.0_IDEA.md) mô tả giả thuyết thiết kế; tài liệu này mô tả **hành vi code hiện tại**.

Mặc định hiện nay là **no-contract**: COPROMEM vẫn phân rã task và dùng memory, nhưng không chèn hướng dẫn “prompt contract”/veto vào prompt agent. Điều này giúp thí nghiệm đối chiếu với ReasoningBank tập trung vào decomposition + memory. Chế độ contract vẫn có để ablation, chỉ bật khi chỉ định `--contract_guidance` hoặc `include_contract_guidance=True`. Các kiểu dữ liệu/schema và kiểm tra nội bộ vẫn tồn tại; “no-contract” chỉ nói về guidance đưa vào prompt, không có nghĩa bỏ mọi ràng buộc của chương trình.

## Luồng hoạt động

1. `RecursiveTaskDecomposer` (`src/copromem/decomposition.py`) đánh giá độ phức tạp, tìm schema/memory phù hợp rồi tạo kế hoạch phân cấp; có nhánh dự phòng khi LLM không trả được phân rã hợp lệ.
2. `COPROMEMMemoryModule` (`src/copromem/copromem_memory_module.py`) nạp trí nhớ thủ tục, chọn mục liên quan và xây phần ngữ cảnh gửi cho agent. `pattern_separation.py` giúp loại/giảm ưu tiên những tình huống trông giống nhau nhưng có khác biệt quan trọng.
3. `schema.py` biểu diễn đồ thị phụ thuộc, node và cạnh; `bank.py` giữ schema cùng episode ngắn hạn, chọn mẫu để củng cố; `credit_assignment.py` phân loại tín hiệu lỗi cấu trúc. `contracts.py` phục vụ chế độ contract tùy chọn và các thí nghiệm cũ.
4. Adapter WebArena (`integrations/reasoning_bank/copromem_adapter.py`) nối bộ nhớ COPROMEM với vòng lặp BrowserGym/ReasoningBank. Sau mỗi task, runner lưu kết quả, cập nhật episode/memory và viết report. Nhánh ReasoningBank dùng logic memory của upstream trên **cùng harness đã được patch** để hai nhánh chạy được qua cùng API/model.

Phân rã/memory là cơ chế định hướng agent, không bảo đảm agent sẽ làm đúng từng bước. Kiểm tra browser action và điểm cuối task đến từ BrowserGym/WebArena; chưa có bộ xác minh ngữ nghĩa độc lập cho mọi milestone của đồ thị. Các claim trong IDEA như tránh hoàn toàn negative transfer phải được kiểm chứng bằng thí nghiệm, không phải thuộc tính đã chứng minh của code.

## Cài đặt

Ví dụ với Python 3.11 và Conda (môi trường `copromem` đang được dùng để phát triển):

```bash
conda create -n copromem python=3.11
conda activate copromem
python -m pip install -e '.[test,benchmark]'
python -m playwright install chromium
bash scripts/setup_reasoningbank.sh
```

Script setup lấy ReasoningBank từ `google-research/reasoning-bank` tại commit `ed80611`, áp dụng patch được lưu trong `integrations/reasoning_bank/upstream.patch`, rồi cài adapter. Script chạy lại được nếu checkout đã đúng trạng thái; không ghi đè thay đổi xung đột. Có thể đặt `REASONING_BANK_SOURCE` thành một Git mirror cục bộ và truyền thư mục checkout làm tham số thứ nhất. Không cần (và không khuyến nghị) `pip install -e external/reasoning-bank`: dependency dùng ở đây nằm trong extra `benchmark` của project.

Benchmark thật còn cần **WebArena Shopping Admin** đang chạy và dữ liệu/config task của upstream trong checkout; repository này không đóng gói Docker image hay dữ liệu website. Mặc định URL là `http://localhost:7780/admin`; nếu khác, đặt `WA_SHOPPING_ADMIN` và `SHOPPING_ADMIN` cho đúng. Kiểm tra website và dữ liệu theo hướng dẫn WebArena/ReasoningBank upstream trước khi gọi API; các task có thể reset/chỉnh dữ liệu website. Nếu chỉ chạy unit test hoặc demo synthetic thì không cần website/API key.

Đặt `OPENROUTER_API_KEY` trong môi trường hoặc trong file `.env` ở repo root (file này bị Git ignore). Mẫu không chứa khóa thật: [`.env.example`](.env.example). Model trong các ví dụ là `deepseek/deepseek-v4.1-flash`; khả dụng và giá của model phụ thuộc tài khoản/provider vào thời điểm chạy.

## Kiểm thử và chạy thử không dùng browser

```bash
python -m pytest
python -m copromem.experiment --seed 42 --output artifacts/synthetic_report.json
```

Demo synthetic kiểm tra các thành phần nghiên cứu cũ, **không** đại diện cho benchmark no-contract hoặc WebArena. Các test contract vẫn chủ động bật mode đó để giữ coverage, trong khi API sản phẩm mặc định no-contract.

## Head-to-head WebArena Shopping Admin

Chạy 30 task dễ–trung bình, hai arm dùng cùng model, cùng giới hạn 25 bước, chạy xen kẽ theo task. Lệnh dưới đây **không** bật contract:

```bash
python scripts/run_head_to_head_nemotron_100.py \
  --tasks easy_medium30 \
  --model_name deepseek/deepseek-v4.1-flash \
  --base_results_dir results_head_to_head_example \
  --report_file results_head_to_head_example/report_head_to_head.md \
  --max_steps 25 --timeout 600
```

Runner tự cập nhật report head-to-head sau mỗi arm và mỗi cặp task, cùng artifacts dưới `results_head_to_head_example/copromem/` và `results_head_to_head_example/reasoningbank/`. Không cần chạy monitor riêng để có live report; `scripts/live_monitor.py` là reporter cho một arm, không dùng nó ghi đè file head-to-head. Các thư mục `results_*/`, `memories_*/`, `external/` và `.env` là dữ liệu cục bộ, không được commit.

Để tiếp tục **cùng protocol** từ 30 task sang toàn bộ task trong [`benchmark_tasks_pure_qa_86.json`](benchmark_tasks_pure_qa_86.json), dùng **cùng** `base_results_dir`/`report_file` và đổi `--tasks qa86_continue`. Runner giữ thứ tự 30 task đầu, bỏ qua arm có `summary_info.json`, rồi chạy phần còn lại trong manifest. Dùng một thư mục kết quả **mới** nếu muốn chạy 86 task từ đầu. Task bị dừng khi chưa có summary có thể phải chạy lại; xem thư mục task/artifacts trước khi resume. Tránh dùng `--tasks qa86` để nối thí nghiệm này vì nó có đường khởi tạo memory khác (`qa86_continue` mới dành cho protocol 30→86).

Chỉ khi cần so sánh chế độ contract, thêm `--contract_guidance` và chọn **thư mục kết quả mới**. Không trộn hai mode vào cùng thư mục, vì runner bỏ qua arm đã hoàn thành theo `summary_info.json`. Cờ `--no_contract_guidance` vẫn được giữ để tương thích, nhưng hiện là mặc định.

## Đọc kết quả và giới hạn thực nghiệm

Report `report_head_to_head.md` là báo cáo **đang cập nhật**: số liệu chỉ nên so trên các cặp task mà cả hai arm đã hoàn thành. Task chưa xong/đang chạy không phải một thất bại đã được chấm. Một số số liệu chi phí/bước là ước lượng theo heuristic, không thay thế hóa đơn provider. Report trong workspace từng bị dừng giữa chừng không được đưa vào Git và không nên diễn giải như kết quả của đủ 86 task.

“ReasoningBank baseline” ở đây là logic memory ReasoningBank trên checkout upstream **đã patch để tích hợp BrowserGym/OpenRouter và hỗ trợ cùng harness**; không phải release upstream nguyên trạng. Patch và commit upstream được lưu trong repo để tái lập. Benchmark vẫn chịu ảnh hưởng bởi tính ngẫu nhiên của model, trạng thái website, episode memory tích lũy, thứ tự task và thay đổi phía provider. Muốn kết luận về hiệu năng nên chạy nhiều seed/lần độc lập, chốt dữ liệu/môi trường và phân tích theo từng task, không chỉ nhìn một tỷ lệ thắng tổng.

## Các file chính

| Đường dẫn | Vai trò |
| --- | --- |
| `docs/COPROMEM_2.0_IDEA.md` | Ý tưởng, mục tiêu nghiên cứu; không phải danh sách tính năng đã bảo đảm |
| `src/copromem/decomposition.py` | Phân rã task và kế hoạch phân cấp |
| `src/copromem/copromem_memory_module.py` | Nạp/truy xuất trí nhớ và tạo context cho agent |
| `src/copromem/schema.py`, `bank.py`, `pattern_separation.py`, `credit_assignment.py` | Schema, quản lý memory, phân biệt tình huống, tín hiệu lỗi |
| `src/copromem/webarena_browsergym_benchmark.py` | Tích hợp benchmark BrowserGym trong package |
| `scripts/run_head_to_head_nemotron_100.py`, `scripts/live_monitor.py` | Runner head-to-head và report trực tiếp (tên script lịch sử, không ràng buộc model Nemotron) |
| `integrations/reasoning_bank/`, `scripts/setup_reasoningbank.sh` | Patch/adapter và quy trình dựng dependency upstream |
| `benchmark_tasks_pure_qa_86.json`, `tests/` | Manifest task và kiểm thử |

Tài liệu cũ được lưu ở [`docs/README_legacy.md`](docs/README_legacy.md) để đối chiếu lịch sử; một số claim và lệnh trong đó đã lỗi thời. Dùng README này làm hướng dẫn chạy hiện hành.
