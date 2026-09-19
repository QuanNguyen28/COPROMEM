# COPROMEM 2.0: Causal & Structural Procedural Memory

> **Tuyên ngôn cốt lõi:** Thay vì bắt Agent ghi nhớ vẹt các lời giải trong quá khứ (*Memory of Solutions*), hãy dạy Agent **học và tích lũy cấu trúc phân rã của bài toán** (*Memory of Task Structure*).

---

## 1. Một Phút Nắm Trọn Ý Tưởng (The 1-Minute Pitch)

Hầu hết các hệ thống AI Agent hiện nay (2023–2026) đang quản lý trí nhớ như một **cuốn nhật ký**:
* Gặp bài toán $\rightarrow$ Giải $\rightarrow$ Lưu lại toàn bộ đoạn chat (*Synapse*) hoặc viết vài dòng tự kiểm điểm bằng chữ (*Reflexion, ReasoningBank*).
* Mỗi khi gặp bài toán phức tạp, Agent lại phải **mò mẫm chia nhỏ nhiệm vụ từ đầu** (*ADaPT, AdaPlan-H*).

**Hậu quả:** 
1. Câu chữ giống nhau một chút là Agent lôi kinh nghiệm cũ ra áp dụng bừa bãi (**Negative Transfer**).
2. Khi thất bại, Agent tự kiểm điểm vu vơ và đổ lỗi lung tung.
3. Cứ thêm 1 kinh nghiệm mới là bộ nhớ lại bị rung lắc, ghi đè làm hỏng các quy tắc cũ (**Catastrophic Interference**).

**Đột phá của COPROMEM 2.0:**
Biến việc **chia nhỏ bài toán** thành một **Vật Thể Trí Nhớ Độc Lập (Decomposition Schema)**:
* Một sơ đồ đồ thị (DAG) chỉ rõ nhiệm vụ nào phụ thuộc vào nhiệm vụ nào.
* Kèm theo **Hợp đồng bàn giao (Handoff Contract)**: Bước A giao việc cho Bước B thì bắt buộc phải thỏa mãn điều kiện gì.
* Tự động phát hiện hai bài toán có câu từ giống nhau nhưng bản chất khác nhau để **tách riêng (Pattern Separation)**.
* Khi thất bại, **chỉ mặt đặt tên đúng 1 trong 4 nguyên nhân** để sửa đúng chỗ, không phá vỡ cấu trúc tổng thể.

---

## 2. Phép Ẩn Dụ Thực Tế: Chuyện Tech Lead & Bản Thiết Kế

Để hiểu bản chất của COPROMEM 2.0, hãy hình dung Agent như một **Công ty Công nghệ**:

```text
               ┌────────────────────────────────────────────────────────┐
               │              TECH LEAD (Decomposition Schema)          │
               │   - Lập bản vẽ kiến trúc (DAG)                         │
               │   - Đặt điều kiện nghiệm thu tại mỗi cổng bàn giao     │
               └───────────────┬────────────────────────┬───────────────┘
                               │                        │
                    Giao việc  │                        │  Giao việc
                               ▼                        ▼
                   ┌───────────────────────┐ ┌───────────────────────┐
                   │    BACKEND DEV (T1)   │ │    FRONTEND DEV (T2)  │
                   └───────────┬───────────┘ └───────────┬───────────┘
                               │                         │
                               └───────────┬─────────────┘
                                           │ Bàn giao API (Handoff)
                                           ▼
                               ┌───────────────────────┐
                               │  GATE CHECK / CONTRACT│
                               │  - API có đủ field?   │
                               │  - Đúng spec không?   │
                               └───────────┬───────────┘
                                           │ Pass
                                           ▼
                               ┌───────────────────────┐
                               │     QA TESTER (T3)    │
                               └───────────────────────┘
```

* **Không làm như cách cũ:** Bạn không bắt nhân viên đọc lại toàn bộ hàng nghìn trang tin nhắn Slack của dự án năm ngoái (quá tải context và nhiễu).
* **Cách làm của COPROMEM 2.0:** Bạn lưu trữ **Bản vẽ quy trình phối hợp (Blueprint)** và **Quy tắc nghiệm thu tại cổng (Handoff Contract)**.
* **Pattern Separation:** Làm "App Ngân Hàng" và "App Đặt Đồ Ăn" đều có tính năng "Thanh Toán". Nhưng ở App Ngân Hàng, bước kiểm tra sinh trắc học bắt buộc phải chạy trước; còn App Đồ Ăn thì chọn mã giảm giá trước. Nếu chỉ tìm kiếm theo từ khóa "Thanh toán", người ta sẽ lấy nhầm quy trình của nhau. Hệ thống nhận diện sự xung đột này để ép tách thành 2 bản vẽ khác nhau.
* **Structural Credit Assignment:** Khi sản phẩm bị lỗi, Tech Lead không nói chung chung "Công ty làm ăn chán quá". Họ tra cứu chính xác:
  1. Do Backend bàn giao thiếu data? (*Handoff Error*)
  2. Do Frontend gọi API trước khi Backend tạo xong? (*Dependency Error*)
  3. Do áp dụng nhầm quy trình của dự án khác? (*Scope Error*)
  4. Hay quy trình chuẩn hết, chỉ do cậu dev gõ nhầm dấu phẩy? (*Leaf Error*)
* **CLS Replay:** Cuối tuần họp Retro (ngoại tuyến). Chỉ những sự cố thực sự có tính bài học sâu sắc mới được cập nhật vào "Quy trình chuẩn của công ty", không sửa quy trình tổng chỉ vì một hôm mạng văn phòng bị rớt.

---

## 3. Vì Sao Các Phương Pháp Hiện Tại Bị "Kẹt"?

| Vấn đề của SOTA hiện tại | Biểu hiện cụ thể | COPROMEM 2.0 giải quyết thế nào? |
|---|---|---|
| **Bẫy RAG Bề Mặt** *(Negative Transfer)* | Hai bài toán có câu từ giống nhau 90% nhưng logic ngược nhau. RAG lôi quy trình cũ ra chạy $\rightarrow$ **Thất bại thảm hại**. | **Pattern Separation**: Đo khoảng cách đồ thị nhân quả ($D_{\text{causal}}$). Nếu câu chữ giống mà đồ thị xung đột $\rightarrow$ Tách đôi schema ngay lập tức. |
| **Bẫy Phản Tư Vu Vơ** *(Vague Reflection)* | Khi thất bại, Agent tự kiểm điểm chung chung bằng văn bản. Thường đổ lỗi sai (lỗi do chia việc thì lại đi sửa câu lệnh prompt). | **4-Tier Credit Assignment**: Truy vết lỗi theo cây quyết định 4 tầng. Lỗi tầng nào sửa tầng đó, giữ nguyên các tầng còn lại. |
| **Bẫy Rung Lắc Bộ Nhớ** *(Catastrophic Interference)* | Chạy xong 1 task là cập nhật bộ nhớ ngay lập tức. Gặp 1 ca ngoại lệ (outlier) là ghi đè, làm hỏng các bài toán bình thường khác. | **CLS Fast/Slow Memory**: Lưu trajectory thô vào bộ nhớ tạm. Chỉ củng cố vào bộ nhớ chậm ngoại tuyến khi đạt điểm ưu tiên cao (Need $\times$ Gain $\times$ Surprise). |
| **Bẫy Khóa Chặt Suy Nghĩ** *(Retrieval Lock-in)* | Một phương án từng đúng 1 lần sẽ liên tục được chọn lại, dập tắt mọi phương án khác, triệt tiêu tính sáng tạo. | **Anti-Lock-in Retrieval**: Luôn trả về 1 phương án tối ưu + 1 phương án cấu trúc khác biệt + 1 nhánh tự do khám phá. |

---

## 4. Bốn Trụ Cột Đột Phá Của COPROMEM 2.0

### Trụ cột 1: Decomposition Schema là Vật Thể Trí Nhớ Hạng Nhất
Không sinh kế hoạch rồi vứt đi sau mỗi lượt chạy. Kế hoạch phân rã được lưu lại thành một cấu trúc dữ liệu đồ thị DAG bền vững:
```yaml
DecompositionSchema:
  task_family: "Multi-Table Data Aggregation"
  nodes: [T1_Planner, T2_Solver, T3_Reviewer]
  edges: [T1 -> T2, T2 -> T3]
  handoff_contracts:
    T1_to_T2:
      precondition: "Plan phải chứa ràng buộc số dòng (cardinality)"
      verifier: "CheckCardinalityPresent"
      recovery: "Yêu cầu Planner bổ sung trước khi chuyển sang Solver"
  transfer_reliability: 0.95
```

### Trụ cột 2: Engine Phân Tách Mẫu (Pattern Separation)
Lấy cảm hứng từ vùng Hồi hải mã của não người. Đo độ tương đồng ngữ nghĩa bằng $S_{\text{semantic}}$ và khoảng cách đồ thị nhân quả bằng $D_{\text{causal}}$:
$$\text{Trigger Separation} = \text{True} \quad \Longleftrightarrow \quad S_{\text{semantic}} \ge 0.40 \quad \text{và} \quad D_{\text{causal}} \ge 0.35$$
Khi phát hiện rủi ro "bẫy ngữ nghĩa", hệ thống lập tức phân nhánh và đưa task vào danh sách cấm (*counterexamples*) của schema cũ.

### Trụ cột 3: Quy Gán Lỗi Cấu Trúc 4 Tầng (Structural Credit Assignment)
Chẩn đoán chính xác nguyên nhân gốc rễ:
1. **Tier 1 (Handoff Violation):** Dữ liệu qua cổng bàn giao không đạt hợp đồng verifier $\rightarrow$ Kích hoạt tuyến phục hồi (recovery route).
2. **Tier 2 (Dependency Conflict):** Bước sau thiếu dữ liệu từ bước trước $\rightarrow$ Thêm cạnh phụ thuộc vào đồ thị DAG.
3. **Tier 3 (Scope Mismatch):** Áp dụng nhầm hợp đồng cho tác vụ ngoại lệ $\rightarrow$ Cập nhật điều kiện phủ quyết (veto).
4. **Tier 4 (Leaf Execution Error):** Quy trình đúng 100%, chỉ do model ở tầng lá giải toán sai $\rightarrow$ Chỉ sửa prompt/skill tầng lá, **giữ nguyên toàn bộ cấu trúc phân rã bên trên**.

### Trụ cột 4: Bộ Nhớ Hai Tầng CLS & Replay Ngoại Tuyến Có Ưu Tiên
Mô phỏng hệ thống học bổ trợ của não bộ:
* **Bộ nhớ nhanh (Fast Episodic Buffer):** Ghi nhận tức thời mọi trajectory thô cùng nhãn lỗi 4 tầng.
* **Bộ nhớ chậm (Slow Consolidated Schema Bank):** Chỉ lưu các quy trình đã được chứng minh bền vững.
* **Điểm ưu tiên Replay (Công thức Mattar–Daw mở rộng):**
  $$\text{Priority} = \text{Need} \times \text{Gain} \times (1 + \text{Surprise}) \times (1 + \text{Uncertainty})$$
  Ưu tiên mổ xẻ các ca **thất bại bất ngờ** và các bài toán có **độ bất định cấu trúc cao** trong pha ngoại tuyến.

---

## 5. Sơ Đồ Dòng Chảy Quyết Định (Decision Dataflow)

```text
               [ NHẬN NHIỆM VỤ MỚI: T_new ]
                            │
                            ▼
           [ DUAL RETRIEVAL: Ngữ Nghĩa & Đồ Thị ]
                            │
            ┌───────────────┴───────────────┐
            │                               │
    Trùng cả Ngữ nghĩa              Trùng Ngữ nghĩa nhưng
     & Logic Nhân quả                 Xung đột Nhân quả
            │                               │
            ▼                               ▼
    [ CHỌN SCHEMA CŨ ]             [ PATTERN SEPARATION ]
            │                      (Tạo Schema Biến thể mới,
            │                       Chống Negative Transfer)
            │                               │
            └───────────────┬───────────────┘
                            ▼
           [ THỰC THI & KIỂM CHỨNG TẠI CỔNG (HANDOFF) ]
           - Handoff Contract kiểm tra từng bước
           - Phát hiện thiếu sót -> Yêu cầu sửa ngay tại chỗ
                            │
                            ▼
                     [ KẾT THÚC TASK ]
                            │
            ┌───────────────┴───────────────┐
            │                               │
         Thành công                      Thất bại
            │                               │
            │                               ▼
            │               [ 4-TIER CREDIT ASSIGNMENT ]
            │               - Handoff hay Dependency?
            │               - Scope hay Leaf Executor?
            │                               │
            └───────────────┬───────────────┘
                            ▼
             [ LƯU VÀO BỘ NHỚ TẠM (FAST STORE) ]
                            │
                            ▼
        [ HỌP RETRO NGOẠI TUYẾN (PRIORITIZED REPLAY) ]
       Replay các ca Surprise cao: Need × Gain × Surprise
                            │
                            ▼
        [ CỦNG CỐ VÀO BỘ NHỚ CHẬM (SLOW SCHEMA BANK) ]
```

---

## 6. Bảng "Vũ Khí Cạnh Tranh" Đối Đầu Reviewer

Khi gửi bài báo đến các hội nghị hàng đầu (ICLR / NeurIPS / ACL), bảng so sánh này chứng minh tính mới tuyệt đối của COPROMEM 2.0:

| Tiêu chí so sánh | Các bài Procedural Memory<br>*(AWM, ReMe, MemP, LEGOMem)* | Các bài Adaptive Decomposition<br>*(ADaPT, AdaPlan-H, Least-to-Most)* | **COPROMEM 2.0**<br>*(Phương pháp đề xuất)* |
|---|---|---|---|
| **Dạng tri thức lưu trữ** | Text kịch bản, đoạn chat, hoặc code API | Không lưu trí nhớ dài hạn (chia lại từ đầu mỗi task) | **Decomposition Schema (Đồ thị DAG + Handoff Contract có điều kiện)** |
| **Xử lý khi 2 task giống câu chữ nhưng khác bản chất** | Bị lừa bởi RAG $\rightarrow$ **Negative Transfer** | Không phát hiện được do không có bộ nhớ đối chiếu | **Pattern Separation tự động phân tách 2 cấu trúc khác biệt** |
| **Cách xử lý thất bại** | Viết tự kiểm điểm bằng văn bản chung chung | Thử phân rã sâu hơn hoặc đổi prompt | **Chẩn đoán chính xác 4 tầng (Handoff, Edge, Scope, Leaf)** |
| **Cơ chế chống quên thảm họa** | Cắt tỉa (pruning) heuristic theo tần suất | Không áp dụng | **Học 2 tầng CLS + Replay ngoại tuyến ưu tiên theo Mattar–Daw** |
| **Bảo toàn tính sáng tạo** | Dễ bị kẹt vào Top-1 (Retrieval Lock-in) | Không lưu trí nhớ | **Anti-Lock-in Retrieval: Trả về cả Schema khai thác và Schema đối trọng** |

---

## 7. Tóm Tắt Trong 1 Câu (Final Takeaway)

> **COPROMEM 2.0 biến Agent từ một kẻ ghi chép nhật ký thụ động thành một Kiến trúc sư trưởng: biết vẽ quy trình phối hợp, biết đặt chốt kiểm soát tại điểm bàn giao, biết phân biệt các bài toán đánh lừa, và biết bắt đúng lỗi để nâng cấp hệ thống một cách có chọn lọc.**
