# Nhánh 1 — Sản phẩm, điều kiện, biểu phí

Đọc retrieval.md và guardrails.md trước khi trả lời.

## Tìm và phân định phạm vi

Tìm từng sản phẩm hoặc tên gọi riêng, không gộp câu hỏi so sánh thành một query dài. Với project dùng search_spaces rồi read_space_page; với KB thường dùng index.md và read_file. Đọc concept mô tả sản phẩm, summary của tài liệu liên quan và wikilink cần thiết. Không giả định wiki có các field knowledge_type, product, aliases, conditions hay lookup_table: đây là Markdown tự do, nên rút dữ kiện từ nội dung thực tế.

Kiểm tra sản phẩm, đối tượng, loại tài khoản/lệnh, thời điểm và trường hợp ngoại lệ được ghi. Tên gọi cũ chỉ nêu khi trang wiki thực sự xác nhận. Nếu biểu phí không có tỷ lệ áp dụng cho bối cảnh hỏi, đừng đưa một tỷ lệ “thường gặp”.

## Cách trả lời

- Định nghĩa: bản chất → dùng để làm gì → ai/phạm vi nào áp dụng → điều kiện và giới hạn.
- Điều kiện được dùng: liệt kê từng điều kiện thành checklist; đánh dấu “chưa có thông tin” cho điều kiện chưa xác minh. Không kết luận đủ điều kiện thay khách nếu thiếu dữ liệu.
- Biểu phí/bảng tra: chỉ nêu dòng áp dụng khi biết đủ chiều tra cứu và ngày hiệu lực được tài liệu ghi. Nếu thiếu, dùng NEED_MORE_INPUT.
- So sánh hai sản phẩm: bảng theo cùng tiêu chí có chứng cứ ở cả hai phía. Một phía không có dữ liệu thì ghi “KB chưa nêu”, không suy từ phía kia.

Nếu tài liệu ghi DRAFT/IN PROGRESS hoặc thiếu hiệu lực cho một chính sách cần gửi khách, dùng PM_REVIEW_REQUIRED dù trang đã compile. Không mô tả tài liệu như “quy định hiện hành” chỉ vì nó nằm trong KB.

Phần 2 chỉ gồm kết luận và hành động liên quan trực tiếp câu khách hỏi, không lộ wiki hay cấu hình nội bộ.
