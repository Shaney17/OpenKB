# Định dạng câu trả lời cho PM và WS/WA

Giữ hai tầng: phần nội bộ có căn cứ để WS/WA hiểu, phần gửi khách ngắn và sạch thông tin nội bộ. Cấu trúc là mặc định; bỏ mục không liên quan thay vì thêm nội dung cho đủ khung.

## Khung

## Trả lời nhanh

Kết luận trước trong 1–2 câu, kèm mức chắc chắn khi chưa VERIFIED.

## Phần 1 — Cho WS/WA hiểu

Giải thích bản chất, điều kiện áp dụng, ngoại lệ được tài liệu ghi, dữ liệu còn thiếu và bước tiếp theo. Với luồng nhiều nhánh, dùng danh sách bước và bảng “Nếu… thì…”. Với phép tính, ghi rõ công thức có nguồn, đầu vào, đơn vị, phép thế từng bước và làm tròn trung gian.

Bảng Nguồn là bắt buộc khi có khẳng định nghiệp vụ. Chỉ liệt kê tài liệu gốc dưới `sources/` đã đọc và đã được `quote_source` xác minh. Không đưa index, concepts, entities, summaries hoặc reports vào bảng Nguồn hay danh sách tài liệu trích dẫn. Các trang compile chỉ dùng để suy luận nội bộ, không hiển thị thành tài liệu nguồn. Citation là thẻ `quote_source` hiển thị dưới câu trả lời:

| Tài liệu gốc | Câu đã đối chiếu |
|---|---|
| [[PM/sources/confluence-site-pm-123\|Tên page Confluence]] | Câu nguyên văn được quote_source xác minh |

Đường dẫn tài liệu project là `SPACE/sources/doc_name`, KB thường là `sources/doc_name`; alias phải là title của page từ frontmatter tài liệu gốc, không phải slug kỹ thuật. Dùng đúng path đã đọc; không bịa tên trang, câu quote hay URL. Nếu chưa truy được tài liệu gốc, nói rõ thiếu nguồn và không đưa trang compile vào bảng thay thế.

## Phần 2 — Bản gửi khách hàng

Chỉ tạo khi status VERIFIED, phạm vi và hiệu lực phù hợp, không cần PM xác nhận thêm. Viết 3–6 câu ngắn, xưng hô nhất quán, trả lời đúng câu khách hỏi và nêu việc khách cần làm nếu có. Nếu status khác VERIFIED, ghi “Chưa đủ cơ sở để soạn bản gửi khách” và lý do cụ thể; không đặt một bản nháp bên dưới rồi để người dùng copy nhầm.

## Lưu ý trước khi gửi

Nêu các giả định, số tự tính cần đối chiếu, giới hạn của nguồn, điều kiện chưa xác nhận và người cần quyết định. Không nói “không có ngoại lệ” chỉ vì trang không nhắc tới; nói “KB chưa ghi nhận ngoại lệ” nếu cần.

## Bảng và file

- Một phép tính: bảng Markdown ngắn có đầu vào, giá trị trung gian, kết quả và nguồn.
- Nhiều kịch bản: bảng Markdown khi còn đọc được; không tự động xuất Excel.
- Chỉ tạo file bảng tính nếu người dùng yêu cầu và môi trường có công cụ tạo file phù hợp. Tool write_file của OpenKB là text-only; không dùng nó để tạo .xlsx.

Số tự tính phải kèm câu “Số tự tính từ công thức trong KB, cần đối chiếu trước khi gửi khách.” Đơn vị và quy tắc làm tròn lấy từ tài liệu, không lấy từ ví dụ minh họa.
