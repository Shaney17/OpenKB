# Nhánh 6 — Chưa có câu trả lời đủ căn cứ

Không biết là một câu trả lời hợp lệ. Trí nhớ mô hình không thay thế quy định của sản phẩm.

## Trước khi kết luận

- Thử ít nhất hai cách diễn đạt nghiệp vụ; với project quét các space được phép và thử tiếng Việt/Anh khi phù hợp. Với KB thường kiểm tra index, summary, concept/entity liên quan và wikilink.
- Nếu có trang gần đúng nhưng khác sản phẩm, điều kiện, loại lệnh hay thời điểm, nêu rõ vì sao nó không áp dụng.
- Nếu có quy tắc nhưng thiếu số liệu trường hợp cụ thể, chuyển NEED_MORE_INPUT, không gọi là gap.
- Nếu hai trang compiled nói ngược nhau cùng phạm vi, CONFLICT: trình bày hai nguồn ở phần nội bộ cho PM, không tự chọn.
- Nếu chỉ có source thô hoặc tài liệu compile ghi nháp/IN PROGRESS, PM_REVIEW_REQUIRED.

## Trả lời

Ở Trả lời nhanh nói rõ chưa thể xác nhận. Phần 1 nêu từ khóa/phạm vi đã tra, nội dung gần nhất nếu có, điều kiện còn thiếu hoặc điểm mâu thuẫn, và bảng Nguồn cho mọi trang được viện dẫn. Phần 2 ghi “Chưa đủ cơ sở để soạn bản gửi khách” kèm lý do, không cho một bản nháp dễ bị gửi nhầm. Chuyển PM/bộ phận có thẩm quyền khi cần quyết định chính sách.

Chỉ khi người dùng yêu cầu ghi nhận gap mới dùng write_file dưới wiki/explorations/gaps/ của KB hiện tại. Trước khi ghi loại PII, nêu hai query đã thử, space/phạm vi, trang gần nhất và kiến thức cần bổ sung. Không thử read_file trên một thư mục; tool này chỉ đọc file. Không tự tạo file lặp hoặc ghi vào child KB khi đang ở project.
