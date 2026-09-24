import json
from pathlib import Path

with open('benchmark_tasks_pure_qa_86.json', 'r', encoding='utf-8') as f:
    tasks = json.load(f)

md_lines = []
md_lines.append('# WebArena Pure QA & Information Retrieval Benchmark Suite (86 Tasks)')
md_lines.append('')
md_lines.append('> **Tiêu chuẩn lựa chọn:** Bộ dữ liệu bao gồm **86 nhiệm vụ Pure Information Retrieval & QA** trên môi trường `shopping_admin` của WebArena. Toàn bộ các tác vụ có can thiệp/thay đổi DOM (như thêm/xóa sản phẩm, hủy đơn hàng, sửa giá, cập nhật trạng thái đơn với `eval_types: ["program_html"]`) đều đã được **loại bỏ 100%**, chỉ giữ lại các tác vụ truy vấn thông tin thuần túy (`eval_types: ["string_match"]`).')
md_lines.append('')
md_lines.append('---')
md_lines.append('')
md_lines.append('## 1. Phân loại theo Danh mục Nghiệp vụ (Category Breakdown)')
md_lines.append('')
md_lines.append('| STT | Nhóm Danh mục (Category) | Số lượng Tasks | Danh sách Task IDs |')
md_lines.append('| :---: | :--- | :---: | :--- |')

cat_groups = {}
for t in tasks:
    cat = t['category']
    if cat not in cat_groups:
        cat_groups[cat] = []
    cat_groups[cat].append(t['task_id'])

for idx, (cat, tids) in enumerate(sorted(cat_groups.items(), key=lambda x: -len(x[1])), 1):
    tid_str = ', '.join([f'`{tid}`' for tid in tids])
    md_lines.append(f'| {idx} | **{cat}** | {len(tids)} | {tid_str} |')

md_lines.append(f'| **Tổng** | **13 Nhóm nghiệp vụ** | **{len(tasks)}** | Tất cả các task đều là Read-only QA |')
md_lines.append('')
md_lines.append('---')
md_lines.append('')
md_lines.append('## 2. Bảng Danh sách Chi tiết Toàn bộ 86 Pure QA Tasks')
md_lines.append('')
md_lines.append('| # | Task ID | Danh mục Nghiệp vụ | Câu hỏi / Nhiệm vụ (User Intent) | Đáp án chuẩn (Ground Truth) |')
md_lines.append('| :-: | :-: | :--- | :--- | :--- |')

for t in tasks:
    gt = str(t['ground_truth']).replace('|', '\\|')
    intent = t['intent'].replace('|', '\\|')
    md_lines.append(f"| {t['index']} | `{t['task_id']}` | {t['category']} | {intent} | `{gt}` |")

md_lines.append('')
md_lines.append('---')
md_lines.append('')
md_lines.append('## 3. Danh sách mảng Task IDs (Python / Array Format)')
md_lines.append('')
md_lines.append('Dành cho việc import trực tiếp vào scripts hoặc runners:')
md_lines.append('```python')
md_lines.append('QA86_TASKS = [')
md_lines.append('    ' + ', '.join(str(t['task_id']) for t in tasks[:20]) + ',')
md_lines.append('    ' + ', '.join(str(t['task_id']) for t in tasks[20:40]) + ',')
md_lines.append('    ' + ', '.join(str(t['task_id']) for t in tasks[40:60]) + ',')
md_lines.append('    ' + ', '.join(str(t['task_id']) for t in tasks[60:80]) + ',')
md_lines.append('    ' + ', '.join(str(t['task_id']) for t in tasks[80:]) + ',')
md_lines.append(']')
md_lines.append('```')

with open('benchmark_tasks_pure_qa_86.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(md_lines))

print(f'Successfully generated benchmark_tasks_pure_qa_86.md with {len(tasks)} tasks.')
