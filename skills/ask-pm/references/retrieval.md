# Tra cứu đúng wiki OpenKB

Skill này chạy trong OpenKB. Các tool dưới đây là function tool của query/chat agent, không phải MCP. Phạm vi luôn là KB đang mở.

## Hai hình dạng KB

- Project Confluence: wiki cha là container. Gọi search_spaces(query) để tìm trên mọi child space, hoặc truyền spaces_filter khi người dùng chỉ định space. Kết quả có space, path, tier, score và excerpt. Đọc toàn văn bằng read_space_page(space, path). list_spaces cho biết space và trạng thái sync.
- KB thường: đọc read_file("index.md") để định hướng, sau đó gọi read_file(path) riêng cho từng trang concepts/, summaries/ hoặc entities/. Không có search_spaces nếu KB không phải project.

Với project, khi gọi read_space_page, path là đường dẫn bên trong space, ví dụ concepts/order-execution.md. Khi dẫn nguồn trong Workbench, dùng dạng [[concepts/PM/order-execution|Luồng xử lý lệnh]]: loại trang, space, tên trang. Với KB thường, bỏ phần PM. Chỉ dẫn link tới trang đã thực sự đọc. Wikilink ở child wiki không kèm space; giữ nguyên space khi lần theo.

Không coi index cha rỗng là không có tài liệu. Không lấy số lượng hit hoặc điểm tìm kiếm làm độ tin cậy nghiệp vụ.

## Chọn và kiểm chứng nguồn

1. Chuẩn hóa câu hỏi thành từ khóa nghiệp vụ, bỏ PII. Dùng tên sản phẩm, loại lệnh, trạng thái và điều kiện liên quan. Với tài liệu Việt–Anh, thử cả hai ngôn ngữ nếu lượt đầu không ra trang đúng.
2. Từ hit compiled (concepts, entities, summaries), đọc đầy đủ ít nhất trang trực tiếp trả lời. Tìm điều kiện, ngoại lệ, giới hạn phạm vi, đơn vị và ghi chú trạng thái tài liệu. Excerpt không phải bằng chứng.
3. Concept/entity là bản tổng hợp; summary giúp kiểm tra tài liệu gốc. Frontmatter sources của concept dẫn tới summary; full_text của summary dẫn tới source. Nếu cần link Confluence, chỉ lấy source_url từ trang source thực sự đọc.
4. Source là bản nhập thô, không thay cho một trang compiled. Ở autonomous, không đọc source để lập luận. Ở pm_assisted, được đối chiếu nhưng nếu câu trả lời chỉ dựa vào source thì PM_REVIEW_REQUIRED.
5. Tài liệu dài PageIndex: get_page_content chỉ đọc wiki của KB thường. Với project child space, không gọi tool này bằng tên tài liệu của child; nếu summary thiếu chi tiết cần thiết, dừng ở giới hạn bằng chứng hoặc yêu cầu PM kiểm tra nguồn gốc.

Compile là bước tạo wiki bằng LLM, không phải phê duyệt chính sách. Nhãn VERIFIED ở đây chỉ có nghĩa là câu trả lời được chứng thực bởi wiki đã compile và không có dấu hiệu mâu thuẫn/nháp trong các trang đã đọc.

## Status

- VERIFIED: trang compiled đọc toàn văn trả lời trực tiếp, đúng sản phẩm, loại giao dịch và điều kiện; không có dấu hiệu nháp, hết hiệu lực hay xung đột chưa giải quyết.
- NEED_MORE_INPUT: quy tắc có trong wiki nhưng thiếu dữ liệu của trường hợp cụ thể. Giải thích cơ chế, hỏi gộp những đầu vào còn thiếu; không bịa kết quả.
- KNOWLEDGE_GAP: đã thử ít nhất hai cách tìm hợp lý nhưng không có trang compiled giải đáp. Ghi rõ đã tra gì.
- CONFLICT: các trang compiled có quy tắc trái nhau cùng phạm vi; không chọn theo score hay ngày sửa.
- PM_REVIEW_REQUIRED: chỉ có source thô, hoặc tài liệu ghi nháp/IN PROGRESS, không rõ hiệu lực hay phê duyệt cho nội dung cần gửi khách.

Không biến thiếu dữ liệu cá nhân thành knowledge gap. Không biến trang tìm được nhưng khác sản phẩm thành VERIFIED.

## Con số

Công thức, tỷ lệ, đơn vị và quy tắc làm tròn phải có căn cứ trong trang compiled. Không có công thức/rate thì không tính. Khi được tính, trình bày từng phép thế, các bước làm tròn trung gian và ghi: “Số tự tính từ công thức trong KB, cần đối chiếu trước khi gửi khách.” Nếu có công cụ tính đáng tin trong môi trường, vẫn phải đối chiếu cách làm tròn với tài liệu. Không mặc định VND hay ngưỡng kiểm tra hợp lý nếu wiki không ghi.

## Ghi nhận khoảng trống

Chỉ ghi file gap khi người dùng yêu cầu lưu lại hoặc quy trình hiện tại đã cho phép việc đó. Tool write_file của OpenKB chỉ ghi dưới wiki/explorations/ hoặc output/. Trước khi ghi cần tránh PII, dùng đường dẫn trong KB hiện tại; không ghi vào child wiki thông qua project nếu tool không hỗ trợ.
