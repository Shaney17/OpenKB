# Ranh giới nghiệp vụ

## Bằng chứng

- Mọi khẳng định nghiệp vụ trong Phần 1 phải có trang concepts, entities hoặc summaries đã đọc toàn văn. Chỉ có hit tìm kiếm hoặc source thô thì chưa đủ.
- Wiki là bản compile bằng LLM, không phải kho chính sách đã duyệt. Nếu trang ghi IN PROGRESS, DRAFT, ngày hiệu lực không rõ cho câu hỏi nhạy cảm, hoặc các trang mâu thuẫn, yêu cầu PM xác nhận trước khi soạn bản gửi khách.
- Không dùng trí nhớ mô hình, quy định chung ngành tài chính hoặc tài liệu Confluence bên ngoài KB để lấp khoảng trống.
- Không suy rule của LO sang MO, mua sang bán, tài khoản thường sang tiểu khoản khác.
- Ngày updated_at và version của source phản ánh lịch sử tài liệu, không chứng minh ngày hiệu lực nghiệp vụ.

## Con số và chênh lệch

- Công thức, tỷ lệ phí, ngưỡng, đơn vị và làm tròn phải có trong trang compiled. Nếu chỉ có công thức mà thiếu đầu vào, dùng NEED_MORE_INPUT và hỏi tất cả đầu vào còn thiếu trong một lần.
- Số tự tính là minh họa cần đối chiếu, không phải số thu thực tế của khách. Không khẳng định hệ thống sai chỉ vì số tự tính lệch số hiển thị.
- Không tự hứa thời hạn xử lý, hoàn tiền, bồi thường hay cách khắc phục.

## Dữ liệu khách hàng

Không gửi số tài khoản, CCCD, email, số điện thoại, họ tên hay mã lệnh định danh vào query, tên file gap hoặc nội dung file. Thay bằng mô tả nghiệp vụ trung tính. Chỉ dùng các số giao dịch cần thiết cho phép tính và không gắn định danh.

## Hai chế độ

- pm_assisted: PM đang tự đọc. Có thể trình bày giả thuyết và đối chiếu source thô nếu dán nhãn rõ; không biến nó thành câu trả lời chính thức.
- autonomous: có thể đọc source thô để kiểm chứng dữ kiện/trích dẫn từ trang compiled, nhưng không dùng source làm căn cứ duy nhất cho kết luận hay nêu giả thuyết như sự thật. Với CONFLICT, PM_REVIEW_REQUIRED hay KNOWLEDGE_GAP, dừng ở câu trả lời cần xác minh và không tạo bản gửi khách.
- Khi không biết ai sẽ duyệt, chọn autonomous.

Không tự ghi file gap, xuất file hoặc gửi thông tin cho khách nếu người dùng chưa yêu cầu hành động đó.

## Ranh giới hai tầng

Phần 1 cho WS/WA được có wikilink, dẫn nguồn, công thức và thuật ngữ nghiệp vụ cần để hiểu nguyên nhân. Phần 2 là đoạn có thể copy cho khách: không chứa tên field/API nội bộ, đường dẫn wiki, link Confluence, tên space, thông tin cá nhân, hay phán đoán hệ thống có lỗi. Tên sản phẩm chỉ dùng nếu đó là tên công khai đúng trong tài liệu và bối cảnh.
