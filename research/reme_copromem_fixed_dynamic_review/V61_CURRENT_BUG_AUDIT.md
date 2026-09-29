# Lỗi engineering ảnh hưởng phương pháp CoProMem / ReMe v6.1

Kiểm tra mã ngày 2026-09-30. Phạm vi: pipeline tạo memory, retrieval, prompt injection, tính độc lập của arm/trial và tính đúng của bằng chứng dùng để học trong evaluation 007. Không có upstream ReMe/AppWorld hoặc artifact live 007 trong workspace; các kết luận về nội dung prompt ReMe thực tế được ghi riêng.

## Lỗi xác nhận từ code

### P0 — CoProMem Fixed bị nhiễm state Dynamic

Runner dùng `pre=state` cho cả Fixed và Dynamic, rồi thay `state` bằng `post` sau mỗi task (`scripts/run_v61_exploratory_evaluation.py:120-140`). Từ task thứ hai, Fixed có thể nhận schema học từ evaluation trước, trái hợp đồng Fixed chỉ đọc (`research/reme_copromem_fixed_dynamic_review/COPROMEM_V6_ARCHITECTURE.md:15`). Phép so sánh Fixed–Dynamic vì thế không còn đúng.

### P0 — Dynamic v6.1 học bằng pipeline v6 cũ

Bank ban đầu được dựng bằng `build_semantic_graph` → `semantic_plan` → `validate_semantic_plan`, loại call hạ tầng/auth/supervisor và kiểm terminal thuộc domain (`scripts/recover_v61_semantic_graph.py:31-45`; `src/copromem/semantic_graph_v61.py:40-120`). Runner evaluation lại gọi `task_batch_update` của v6, dùng `build_graph` và `plan_task_batch` trực tiếp (`scripts/run_v61_exploratory_evaluation.py:140`; `src/copromem/experiments/reme_copromem/contrastive_v6_runner.py:14-44`). Sau task đầu, Dynamic có thể lưu schema theo tiêu chuẩn khác bank v6.1 ban đầu, kể cả bước phi domain mà v6.1 định loại.

### P0 — Retrieval CoProMem không dùng task hiện tại

`terms` được tính một lần từ terminal effects của bank ban đầu và truyền nguyên cho mọi task/trial (`scripts/run_v61_exploratory_evaluation.py:113,134`). `retrieve` chỉ kiểm terminal/required operations thuộc tập này và chọn candidate tương thích đầu tiên theo ID (`src/copromem/contrastive_graph_v6.py:149-159`). Task khác operation có thể nhận cùng guidance; schema nhiều bước dễ fallback rỗng; schema mới với terminal khác tập ban đầu không được truy xuất. Không có quyết định `compatible/conflict/unknown` theo descriptor task hiện tại.

### P1 — ReMe Dynamic nhận feedback trial 1 trước trial 2 cùng task

Một service `reme-dynamic` phục vụ cả hai trial (`scripts/run_v61_exploratory_evaluation.py:115-135`). Sau scorer của trial 1, callback đưa history và `after_score` vào `summary_memory`, có thể thêm memory và cập nhật metadata (`src/copromem/experiments/reme_copromem/runner.py:268-310`; `src/copromem/integrations/reme/lifecycle.py:21-47`). Trial 2 dùng lại service đã cập nhật, nên hai seed cùng task không độc lập; chính sách này cũng khác CoProMem, vốn cập nhật sau cả task. **Đường dữ liệu đã xác nhận;** memory nào được retrieval vào prompt thực tế chưa xác nhận vì thiếu upstream/artifact live.

### P1 — CoProMem Dynamic không chọn procedure candidate tốt nhất

Quy tắc đã chốt là các trial cùng task xuất phát từ cùng pre-state và chỉ candidate tốt nhất chuyển sang task kế tiếp. Pipeline hiện lấy ordered common subsequence của **tất cả** graph thành công và yêu cầu tối thiểu hai success; không so cost/actions hoặc chọn winner episode (`src/copromem/contrastive_graph_v6.py:79-145`; `src/copromem/experiments/reme_copromem/contrastive_v6_runner.py:14-23`). Với một trong hai trial thành công, nó không học candidate đó; khi cả hai thành công, nó lưu schema giao nhau, không phải procedure của trial tốt nhất. Winner policy ở `src/copromem/online.py:28-53` không được runner 007 gọi.

### P1 — Guidance trong prompt mất cấu trúc procedure

Schema có `typed_constraints` và provenance graph, nhưng `retrieve` chỉ render `Use public operation constraint: ...` từ `required_operations` (`src/copromem/contrastive_graph_v6.py:112-117,149-163`). Prompt không nhận thứ tự DAG, dataflow, input/output slots, preconditions hoặc checks. Kết quả đo hiện tại chủ yếu là hiệu quả của danh sách tên operation, không kiểm chứng được tác dụng của schema/procedure guidance đầy đủ.

### P1 — Semantic projection có thể làm mất thứ tự bước

`project_graph` gộp các call cùng operation nếu không có dataflow hash trực tiếp, dù giữa chúng có bước khác; nó cũng bỏ order edges và chỉ giữ dataflow edges (`src/copromem/semantic_graph_v61.py:53-80`). Đã tái hiện thuần hàm: `read → write → read` thành `read (multiplicity=2), write` và không còn edge. Nếu write thay đổi trạng thái giữa hai read, procedure học được không phản ánh trajectory thật.

### P1 — Resume có thể làm sai dòng thời gian học online

Runner luôn nạp lại `fixed-bank.json`; artifact cũ bị bỏ qua và không được đưa lại vào batch `copro` (`scripts/run_v61_exploratory_evaluation.py:113,125-140`). Nhánh ReMe Dynamic còn tạo `DynamicUpdateIdentity` thiếu ba tham số, gây `TypeError` khi gặp artifact cũ (`scripts/run_v61_exploratory_evaluation.py:125-128`; `src/copromem/integrations/reme/dynamic_checkpoint.py:56-61`). Sửa riêng exception vẫn chưa khôi phục state CoProMem, nên memory cho task kế tiếp có thể sai.

### P1 — Score dùng để học chưa gắn với scorer cho trajectory có hành động

`task_batch_update` phân success/failure bằng `after_score` trong artifact (`src/copromem/experiments/reme_copromem/contrastive_v6_runner.py:14-23`). Với trajectory có hành động, validator kiểm execution journal nhưng không đối chiếu score artifact với `official_score` trong scorer journal (`src/copromem/experiments/reme_copromem/evidence_contract.py:215-245`; `src/copromem/integrations/reme/upstream_executor.py:115-128`). Đối chiếu score chỉ có ở nhánh zero-action. Artifact ghi sai hoặc bị thay đổi có thể xếp trajectory vào nhóm học sai.

## Rủi ro chưa xác nhận ở runtime này

- ReMe Fixed được nạp qua `load_memory` nhưng runner không dump/so hash clone trước và sau evaluation (`scripts/run_v61_exploratory_evaluation.py:115-117`). Nếu service nạp thiếu hoặc thay đổi bank khi retrieval, baseline thực tế khác bank công bố. Helper kiểm clone đã có (`src/copromem/integrations/reme/bank.py:347-360`) nhưng không dùng ở runner.
- Agent ReMe và AppWorld runtime được chọn qua biến môi trường; executor kiểm class nằm dưới thư mục nguồn chứ không pin nội dung source/scorer (`src/copromem/integrations/reme/upstream_executor.py:18-22,131-151`). Nếu dependency thay đổi giữa run, prompt hoặc scorer có thể đổi dù commit CoProMem giống nhau. Không có upstream trong workspace để xác định drift thực tế.

Không thấy đường đưa ground truth AppWorld trực tiếp vào prompt của trial đang chạy: live request không bật `fixture=True`, scorer được gọi sau vòng hành động và `after_score` không được append vào model history (`src/copromem/benchmarks/appworld/worker.py:51-78`; `src/copromem/experiments/reme_copromem/runner.py:235-268`). Lỗi về khóa tiến trình, tốc độ chạy, test portability và định dạng báo cáo được loại khỏi audit này vì không trực tiếp xác định phương pháp đang được đánh giá.
