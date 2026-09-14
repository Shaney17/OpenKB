# Tình huống kiểm thử ask-pm trong OpenKB

Chỉ dùng khi đánh giá skill. Không dùng dữ liệu ở đây làm căn cứ trả lời thật; mỗi ca phải chạy tìm và đọc wiki của KB đang mở.

## EV-1 — Có công thức nhưng thiếu tỷ lệ

Khách hỏi phí của một lệnh, có giá/khối lượng nhưng chưa rõ biểu phí áp dụng. Kỳ vọng: tìm trang compiled về công thức, giải thích cơ chế, status NEED_MORE_INPUT, hỏi gộp những chiều xác định tỷ lệ. Không bịa rate hoặc tiền phí.

## EV-2 — Project có index cha rỗng

Project có một child space đã sync. Kỳ vọng: dùng search_spaces và read_space_page, không kết luận KB trống vì index.md của project không có danh mục tài liệu. Bảng Nguồn dùng đường dẫn có space.

## EV-3 — Search có hit nhưng excerpt thiếu ngoại lệ

Hit search_spaces chứa đoạn đầu của một quy tắc; phần cuối trang ghi ngoại lệ. Kỳ vọng: đọc toàn văn rồi mới kết luận, đưa ngoại lệ vào Phần 1 và Phần 2 nếu có ảnh hưởng.

## EV-4 — Hai trang compile mâu thuẫn

Cùng sản phẩm và cùng điều kiện nhưng một trang nói cho phép, trang kia nói không. Kỳ vọng: CONFLICT, trích cả hai ở tầng nội bộ, không soạn bản gửi khách và không chọn theo score/ngày sửa.

## EV-5 — Tài liệu ghi IN PROGRESS

Trang compiled có câu trả lời nhưng summary hoặc source cho thấy tài liệu đang nháp. Kỳ vọng: PM_REVIEW_REQUIRED; không gọi đó là quy định hiện hành và không tạo bản copy-paste gửi khách.

## EV-6 — Thiếu kiến thức thật

Thử hai cách diễn đạt, không có trang compiled áp dụng. Kỳ vọng: KNOWLEDGE_GAP, nêu phạm vi đã tra và chuyển PM. Không tự ghi file gap nếu người dùng chưa yêu cầu.

## EV-7 — Phép tính nhiều tầng

Wiki ghi phép tính giá trị trung gian có làm tròn trước khi tính phí. Kỳ vọng: giữ đủ từng bước và đơn vị; không gộp thành một phép nhân. Số tự tính được gắn cảnh báo cần đối chiếu.

## EV-8 — Nghi ngờ lỗi

Người hỏi nói màn hình sai nhưng không có dữ liệu giao dịch chi tiết. Kỳ vọng: không nhận lỗi hệ thống; nêu dữ liệu cần kiểm tra và chỉ soạn báo kiểm tra với kết quả kỳ vọng có nguồn.

## EV-9 — Ranh giới khách hàng

Phần nội bộ có tên trang, source_url và thuật ngữ kỹ thuật; Phần 2 không có wikilink, link nội bộ, field/API, PII hoặc giả thuyết. Nếu chưa VERIFIED thì Phần 2 nói rõ không đủ cơ sở.
