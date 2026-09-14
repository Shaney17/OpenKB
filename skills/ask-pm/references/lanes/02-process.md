# Nhánh 2 — Luồng xử lý và trạng thái

Đọc toàn văn trang concept/summary về quy trình, trạng thái và các wikilink liên quan. Wiki OpenKB là Markdown tự do; không giả định có payload ordered_steps, actors, decision_points hay escalation_paths.

## Dựng luồng nghiệp vụ

1. Xác định điểm bắt đầu và trạng thái mà khách thực sự nhìn thấy.
2. Sắp xếp các bước theo thứ tự tài liệu ghi. Nếu có nhánh LO/MO, mua/bán, thành công/thất bại, tách thành bảng “Nếu… thì…” thay vì gộp thành một luồng.
3. Tách thao tác khách/WS/WA cần biết khỏi bước API, event và microservice nội bộ. Phần 1 giải thích đủ để WS/WA hiểu nguyên nhân; Phần 2 chỉ nêu trạng thái, bước còn lại và việc khách cần làm.
4. Chỉ nêu thời hạn hoặc người/bộ phận xử lý khi trang wiki ghi rõ. Nếu không có, ghi trong Lưu ý trước khi gửi là KB chưa nêu; không tự gán SLA hoặc tuyến escalate.
5. Nếu hai trang mô tả trạng thái hay thứ tự khác nhau trong cùng phạm vi, chuyển CONFLICT. Nếu câu hỏi là số tiền/phí tại một bước, dùng thêm nhánh 3.

Không nói “đã hoàn tất” khi wiki chỉ mô tả “đã tiếp nhận”. Không đồng nhất trạng thái nội bộ với thông báo hiển thị nếu chưa có bảng ánh xạ trong trang đọc được.
