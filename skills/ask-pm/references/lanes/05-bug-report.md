# Nhánh 5 — Soạn báo kiểm tra hiện tượng bất thường

Mục tiêu là một phiếu để PM/kỹ thuật có thể tái hiện và kiểm chứng, không phải chẩn đoán chắc chắn lỗi hệ thống.

## Trước khi viết

Tìm trang compiled về hành vi kỳ vọng, quy trình và ngoại lệ. Đọc toàn văn. Nếu không có căn cứ về “kết quả mong đợi”, ghi rõ “KB chưa xác nhận hành vi mong đợi”; đừng tự đặt rule. Nếu hiện tượng thực ra khớp quy định trong wiki, chuyển nhánh 4 để giải thích thay vì mở bug.

Không dùng tên field/API trong bản gửi khách. Không đưa PII vào query, phiếu hoặc tên file. Nếu cần đối chiếu giao dịch thật, yêu cầu người có quyền kiểm tra trong hệ thống nội bộ; skill không tự truy dữ liệu khách.

## Phiếu nội bộ

- Tóm tắt hiện tượng và mức độ ảnh hưởng được người hỏi mô tả.
- Điều kiện phát sinh: sản phẩm, loại lệnh/giao dịch, trạng thái, thời điểm tương đối, phiên bản ứng dụng nếu người hỏi có.
- Bước tái hiện và kết quả thực tế — chỉ ghi điều đã quan sát/người hỏi cung cấp.
- Kết quả kỳ vọng: trích trang OpenKB đã đọc, hoặc ghi “cần PM xác nhận”.
- Dữ liệu còn thiếu để kiểm tra, nơi có thể lấy; không yêu cầu khách cung cấp thông tin nhạy cảm vào chat.
- Bảng Nguồn với wikilink nội bộ.

Chỉ tạo hoặc lưu file phiếu khi người dùng yêu cầu. Không tự gửi ticket, thông báo cho bên thứ ba, hay hứa SLA. Phần gửi khách, nếu chưa đủ VERIFIED, chỉ soạn câu thông báo đang kiểm tra khi người dùng yêu cầu rõ; không đưa ra nguyên nhân hoặc cam kết.
