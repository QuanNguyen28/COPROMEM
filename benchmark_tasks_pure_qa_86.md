# WebArena Pure QA & Information Retrieval Benchmark Suite (86 Tasks)

> **Tiêu chuẩn lựa chọn:** Bộ dữ liệu bao gồm **86 nhiệm vụ Pure Information Retrieval & QA** trên môi trường `shopping_admin` của WebArena. Toàn bộ các tác vụ có can thiệp/thay đổi DOM (như thêm/xóa sản phẩm, hủy đơn hàng, sửa giá, cập nhật trạng thái đơn với `eval_types: ["program_html"]`) đều đã được **loại bỏ 100%**, chỉ giữ lại các tác vụ truy vấn thông tin thuần túy (`eval_types: ["string_match"]`).

---

## 1. Phân loại theo Danh mục Nghiệp vụ (Category Breakdown)

| STT | Nhóm Danh mục (Category) | Số lượng Tasks | Danh sách Task IDs |
| :---: | :--- | :---: | :--- |
| 1 | **Bestseller & Sales Reports** | 13 | `6`, `0`, `119`, `1`, `3`, `107`, `2`, `4`, `5`, `108`, `109`, `110`, `111` |
| 2 | **Recent Orders & Payment Audit** | 12 | `201`, `198`, `202`, `203`, `200`, `199`, `193`, `194`, `197`, `204`, `196`, `195` |
| 3 | **Unhappy Customer Identification** | 10 | `116`, `112`, `113`, `114`, `115`, `243`, `244`, `245`, `246`, `247` |
| 4 | **Customer Order History & Ranking** | 9 | `94`, `95`, `41`, `42`, `43`, `62`, `63`, `64`, `65` |
| 5 | **Sales & Cancellation Analytics** | 9 | `288`, `128`, `129`, `130`, `131`, `289`, `290`, `291`, `292` |
| 6 | **Inventory & Stock Management** | 5 | `185`, `184`, `186`, `183`, `187` |
| 7 | **Customer Contact & Profile** | 5 | `208`, `209`, `210`, `211`, `212` |
| 8 | **Review Keyword Search** | 5 | `11`, `12`, `13`, `14`, `15` |
| 9 | **Customer Dissatisfaction & Complaints** | 5 | `213`, `214`, `215`, `216`, `217` |
| 10 | **Review Time-Period Analytics** | 5 | `344`, `345`, `346`, `347`, `348` |
| 11 | **Product Positive Feedback** | 4 | `120`, `121`, `122`, `123` |
| 12 | **Review Status Aggregation** | 3 | `77`, `78`, `79` |
| 13 | **Search Terms Analytics** | 1 | `127` |
| **Tổng** | **13 Nhóm nghiệp vụ** | **86** | Tất cả các task đều là Read-only QA |

---

## 2. Bảng Danh sách Chi tiết Toàn bộ 86 Pure QA Tasks

| # | Task ID | Danh mục Nghiệp vụ | Câu hỏi / Nhiệm vụ (User Intent) | Đáp án chuẩn (Ground Truth) |
| :-: | :-: | :--- | :--- | :--- |
| 1 | `94` | Customer Order History & Ranking | Telll me the grand total of invoice 000000001. | `['36.39']` |
| 2 | `95` | Customer Order History & Ranking | Telll me the grand total of invoice 000000002. | `['39.64']` |
| 3 | `41` | Customer Order History & Ranking | List the top 1 search terms in my store | `hollister` |
| 4 | `42` | Customer Order History & Ranking | List the top 2 search terms in my store | `['hollister', 'Joust Bag']` |
| 5 | `43` | Customer Order History & Ranking | List the top 3 search terms in my store | `['hollister', 'Joust Bag', 'Antonia Racer Tank']` |
| 6 | `185` | Inventory & Stock Management | Give me the brand of the products that have 3 units left | `['Eos', 'Minerva']` |
| 7 | `201` | Recent Orders & Payment Audit | Get the customer name of the earliest fraud suspect order | `N/A` |
| 8 | `198` | Recent Orders & Payment Audit | Get the customer name of the most recent cancelled order | `Lily Potter` |
| 9 | `202` | Recent Orders & Payment Audit | Get the date of the most recent canlled order | `May 23, 2023` |
| 10 | `203` | Recent Orders & Payment Audit | Get the purchase date and order id of the most recent pending order | `000000299, May 31, 2023, 2:55:09 AM` |
| 11 | `200` | Recent Orders & Payment Audit | Get the billing name of the oldest complete order | `John Lee` |
| 12 | `184` | Inventory & Stock Management | Give me the name of the products that have 0 units left | `Sinbad Fitness Tank` |
| 13 | `186` | Inventory & Stock Management | Give me the product names and the sizes of the products that have 2-3 units left | `Eos V-Neck Hoodie: S Minera Luma Tech V-Tee: XS` |
| 14 | `199` | Recent Orders & Payment Audit | Get the order ID of the newest pending order | `['299']` |
| 15 | `193` | Recent Orders & Payment Audit | Get the total payment amount of the last 2 completed orders | `['182.4']` |
| 16 | `194` | Recent Orders & Payment Audit | Get the total payment amount of the last 5 completed orders | `['555.2']` |
| 17 | `197` | Recent Orders & Payment Audit | Get the total payment amount of the last 5 non-cancelled orders | `['778.2']` |
| 18 | `6` | Bestseller & Sales Reports | What are the top-5 best-selling product in 2023 | `['Sprite Yoga Strap 6 foot', 'Overnight Duffle', 'Ida Workout Parachute Pant-29-Purple', 'Hawkeye Yoga Short-32-Blue', 'Sprite Stasis Ball 65 cm']` |
| 19 | `204` | Recent Orders & Payment Audit | Get the product name and discounted price (low to high) of the most recent completed order | `Rapha Sports Short: $35 Thorpe Track Pant: $54.4 Mach Street Sweatshirt: $62` |
| 20 | `127` | Search Terms Analytics | What brands appear most frequently among the top search terms? | `['Hollister', 'Joust', 'Antonia']` |
| 21 | `0` | Bestseller & Sales Reports | What is the top-1 best-selling product in 2022 | `Quest Lumaflex™ Band` |
| 22 | `119` | Bestseller & Sales Reports | Tell me the reasons why customers like Antonia Racer Tank | `Its color and style is good` |
| 23 | `1` | Bestseller & Sales Reports | What is the top-1 best-selling brand in Quarter 1 2022 | `Sprite` |
| 24 | `3` | Bestseller & Sales Reports | What are the top-2 best-selling product in 2022 | `['Quest Lumaflex™ Band', 'Sprite Stasis Ball 65 cm']` |
| 25 | `116` | Unhappy Customer Identification | Show me the name of the customers who have expressed dissatisfaction with tanks products? | `['Alexander', 'Carma', 'Dominic', 'Merrie', 'Monroe', 'Scotty', 'Shaunte', 'Teofila', 'Valorie']` |
| 26 | `62` | Customer Order History & Ranking | Which customer has completed the most number of orders in the entire history? | `['Jane Smith']` |
| 27 | `63` | Customer Order History & Ranking | Which customer(s) has completed the second most number of orders in the entire history? | `['Adam Garcia', 'Michael Nguyen', 'Sarah Miller']` |
| 28 | `107` | Bestseller & Sales Reports | Presents the monthly count of successful orders from May to December 2022 in MM:COUNT format | `May: 8 orders June: 13 orders July: 9 orders August: 8 orders Sepetember: 10 orders Octorbor: 4 orders November: 5 orders December: 10 orders  ` |
| 29 | `196` | Recent Orders & Payment Audit | Compare the payment difference of the last 4 cancelled orders and completed orders | `['194.25']` |
| 30 | `288` | Sales & Cancellation Analytics | Tell me the name of the customer who has the most cancellations in the history | `Samantha Jones` |
| 31 | `112` | Unhappy Customer Identification | Show me the customers who have expressed dissatisfaction with Circe fleece? | `Hannah Lim` |
| 32 | `113` | Unhappy Customer Identification | Show me the customers who have expressed dissatisfaction with Olivia zip jacket? | `['Emma Lopez', 'Seam Miller']` |
| 33 | `114` | Unhappy Customer Identification | Show me the customers who have expressed dissatisfaction with Antonia racer tank? | `['Shaunte', 'Merrie']` |
| 34 | `115` | Unhappy Customer Identification | Show me the name of the customers who have expressed dissatisfaction with Chloe tank | `` |
| 35 | `208` | Customer Contact & Profile | Find the customer name and email with phone number +1 2058812302 | `['John Smith', 'john.smith.xyz@gmail.com']` |
| 36 | `209` | Customer Contact & Profile | Find the customer name and email with phone number 2137418080 | `['Jennifer White', 'jennifer.white@yahoo.com']` |
| 37 | `210` | Customer Contact & Profile | Find the customer name and email with phone number 2065555555 | `['Adam Garcia', 'gamingpro456@gmail.com']` |
| 38 | `211` | Customer Contact & Profile | Find the customer name and email with phone number 8015551212 | `['Sean Miller', 'sean.miller@gmail.com']` |
| 39 | `212` | Customer Contact & Profile | Find the customer name and email with phone number 555-229-3326 | `['Veronica Costello', 'roni_cost@example.com']` |
| 40 | `11` | Review Keyword Search | Tell me the the number of reviews that our store received by far that mention term "disappointed" | `['6']` |
| 41 | `12` | Review Keyword Search | Tell me the the number of reviews that our store received by far that mention term "satisfied" | `['2']` |
| 42 | `13` | Review Keyword Search | Tell me the the number of reviews that our store received by far that mention term "decent" | `['2']` |
| 43 | `14` | Review Keyword Search | Tell me the the number of reviews that our store received by far that mention term "not useful" | `['0']` |
| 44 | `15` | Review Keyword Search | Tell me the the number of reviews that our store received by far that mention term "best" | `['2']` |
| 45 | `77` | Review Status Aggregation | What is the total count of Pending reviews amongst all the reviews? | `['5']` |
| 46 | `78` | Review Status Aggregation | What is the total count of Approved reviews amongst all the reviews? | `['346']` |
| 47 | `79` | Review Status Aggregation | What is the total count of Not Approved reviews amongst all the reviews? | `['0']` |
| 48 | `213` | Customer Dissatisfaction & Complaints | What are the key aspects that the customers don't like about Antonia Racer Tank | `Not suitable for high-impact workouts` |
| 49 | `214` | Customer Dissatisfaction & Complaints | What are the key aspects that the customers don't like about Zing Jump Rope | `It is hard to find the right size. Won't last long` |
| 50 | `215` | Customer Dissatisfaction & Complaints | What are the key aspects that the customers don't like about Circe ice fleece | `Material quality, fit, insufficient warmth, color` |
| 51 | `216` | Customer Dissatisfaction & Complaints | What are the key aspects that the customers don't like about Electra Bra Top | `Not true to size` |
| 52 | `217` | Customer Dissatisfaction & Complaints | What are the key aspects that the customers don't like about Pursuit Tone Band | `Insufficient resistance for their workouts.` |
| 53 | `243` | Unhappy Customer Identification | Show me the email address of the customer who is the most unhappy with Circe fleece | `hannah.lim@gmail.com` |
| 54 | `244` | Unhappy Customer Identification | Show me the email address of the customer who is the most unhappy with Olivia zip jacket | `emma.lopez@gmail.com` |
| 55 | `245` | Unhappy Customer Identification | Show me the name of the customer who is the most unhappy with Antonia racer tank | `Shaunte` |
| 56 | `246` | Unhappy Customer Identification | Show me the name of the customer who is the most unhappy with Chloe tank | `Teofila` |
| 57 | `247` | Unhappy Customer Identification | Show me the email address of the customer who is the most unhappy with the style of Zoe products | `N/A` |
| 58 | `120` | Product Positive Feedback | Tell me the reasons why customers like Ana Running Short | `It is comfortable` |
| 59 | `121` | Product Positive Feedback | Tell me the reasons why customers like Circe hooded fleece | `Warm and comfortable. True to size.` |
| 60 | `122` | Product Positive Feedback | Tell me the reasons why customers like Olivia zip jacket | `Lightweight, comfortable, and stylish. Good design and details.` |
| 61 | `123` | Product Positive Feedback | Tell me the reasons why customers like Circe's products | `Warm and comfortable. True to size.` |
| 62 | `344` | Review Time-Period Analytics | How many reviews our shop received by far? | `['351']` |
| 63 | `345` | Review Time-Period Analytics | How many reviews our shop received in Apr 2023? | `['351']` |
| 64 | `346` | Review Time-Period Analytics | How many reviews our shop received during 2022? | `['0']` |
| 65 | `347` | Review Time-Period Analytics | How many reviews our shop received from the beginning of the shop? | `['351']` |
| 66 | `348` | Review Time-Period Analytics | How many reviews our shop received in May 2023? | `['0']` |
| 67 | `128` | Sales & Cancellation Analytics | What's the total number of items sold in the most recent 2 orders? | `['9']` |
| 68 | `129` | Sales & Cancellation Analytics | What's the total number of items sold in the most recent 4 orders? | `['16']` |
| 69 | `130` | Sales & Cancellation Analytics | What's the total number of items sold in the most recent 5 orders? | `['18']` |
| 70 | `131` | Sales & Cancellation Analytics | What's the total number of items sold in the most recent 7 orders? | `['25']` |
| 71 | `289` | Sales & Cancellation Analytics | Tell me the email address, name, phone number of the customer who has the most cancellations in the history | `email: coolcat321@hotmail.com name: Samantha Jones phone number: 3055551212` |
| 72 | `290` | Sales & Cancellation Analytics | Tell me the product SKUs in the most recent cancelled orders of the customer who has the most cancellations in the history | `['WSH09-29-White', 'WSH09-28-Green', 'MSH11-34-Blue', 'WP09-29-Purple']` |
| 73 | `291` | Sales & Cancellation Analytics | Tell me the total spend on products in the most recent cancelled orders of the customer who has the most cancellations in the history | `['148']` |
| 74 | `292` | Sales & Cancellation Analytics | Tell me the total number of cancellations of the customer who has the most cancellations in the history | `['9']` |
| 75 | `183` | Inventory & Stock Management | Give me the SKU of the products that have 10 units left | `There is no product that has 10 quantities left.` |
| 76 | `187` | Inventory & Stock Management | Give me the SKU of the products that have 1-3 units left | `['WH11-S-Blue', 'WS08-XS-Blue']` |
| 77 | `195` | Recent Orders & Payment Audit | Get the total payment amount of the last 5 pending orders | `['885.4']` |
| 78 | `2` | Bestseller & Sales Reports | What is the top-1 best-selling product type in Quarter 1 2022 | `Yoga ball` |
| 79 | `4` | Bestseller & Sales Reports | What are the top-3 best-selling product in Jan 2023 | `['Impulse Duffle', 'Overnight Duffle', 'Hawkeye Yoga Short-32-Blue']` |
| 80 | `5` | Bestseller & Sales Reports | What is the top-1 best-selling product type in Jan 2023 | `Duffle` |
| 81 | `64` | Customer Order History & Ranking | Which customer has placed 2 orders in the entire history? | `['Lisa Kim', 'Lisa Green', 'Julia Williams', 'Brian Smith', 'Alexander Thomas']` |
| 82 | `65` | Customer Order History & Ranking | Which customer has completed the fifth most number of orders in the entire history? | `['Jane Doe']` |
| 83 | `108` | Bestseller & Sales Reports | Presents the monthly count of successful orders 01/2023-05/2023 in MM:COUNT format | `January: 12 orders Febulary: 7 orders March: 5 orders Apirl: 9 orders May: 5 orders` |
| 84 | `109` | Bestseller & Sales Reports | Presents the monthly count of successful orders from Jan to December 2022 in MM:COUNT format | `January: 11 orders Feburary: 16 orders March: 14 orders April: 7 orders May: 8 orders June: 13 orders July: 9 orders August: 8 orders Sepetember: 10 orders Octorbor: 4 orders November: 5 orders December: 10 orders  ` |
| 85 | `110` | Bestseller & Sales Reports | Presents the monthly count of successful orders from Jan to Nov 2022 in MM:COUNT format | `January: 11 orders Feburary: 16 orders March: 14 orders April: 7 orders May: 8 orders June: 13 orders July: 9 orders August: 8 orders Sepetember: 10 orders Octorbor: 4 orders November: 5 orders  ` |
| 86 | `111` | Bestseller & Sales Reports | Presents the monthly count of successful orders from Feb to Nov 2022 in MM:COUNT format | `Feburary: 16 orders March: 14 orders April: 7 orders May: 8 orders June: 13 orders July: 9 orders August: 8 orders Sepetember: 10 orders Octorbor: 4 orders November: 5 orders  ` |

---

## 3. Danh sách mảng Task IDs (Python / Array Format)

Dành cho việc import trực tiếp vào scripts hoặc runners:
```python
QA86_TASKS = [
    94, 95, 41, 42, 43, 185, 201, 198, 202, 203, 200, 184, 186, 199, 193, 194, 197, 6, 204, 127,
    0, 119, 1, 3, 116, 62, 63, 107, 196, 288, 112, 113, 114, 115, 208, 209, 210, 211, 212, 11,
    12, 13, 14, 15, 77, 78, 79, 213, 214, 215, 216, 217, 243, 244, 245, 246, 247, 120, 121, 122,
    123, 344, 345, 346, 347, 348, 128, 129, 130, 131, 289, 290, 291, 292, 183, 187, 195, 2, 4, 5,
    64, 65, 108, 109, 110, 111,
]
```