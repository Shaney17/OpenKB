# Chuyển thuật ngữ kỹ thuật thành lời cho WS/WA và khách

Đọc trang wiki nguyên văn trước, rồi diễn giải mà không làm mất điều kiện hoặc ngoại lệ. Dùng một từ nghiệp vụ nhất quán cho cùng khái niệm. Không xuất tên API, service, event, database, field hoặc luồng nội bộ trong bản gửi khách.

| Wiki có thể ghi | Phần 1 cho WS/WA | Phần 2 cho khách |
|---|---|---|
| Maker / taker | Lệnh chờ sẵn trong sổ / lệnh khớp ngay với lệnh chờ | Vai trò của lệnh khi giao dịch khớp, nếu khách cần biết |
| hold / unhold | Tạm giữ / giải tỏa tiền hoặc tài sản | Số dư tạm giữ / được giải tỏa |
| minNotional | Giá trị giao dịch tối thiểu | Giá trị tối thiểu để đặt lệnh |
| PARTIAL_MATCHED | Lệnh đã khớp một phần | Lệnh đã được thực hiện một phần |
| ORDER_MATCHED hoặc tên microservice | Sự kiện nội bộ xác nhận khớp | Bỏ tên nội bộ, chỉ nêu trạng thái khách thấy |

Không dịch một trạng thái thành cam kết thời gian hoặc kết quả mà wiki không nêu. Không đồng nhất REJECTED với CANCELED khi tài liệu phân biệt. Không tự đoán đồng tiền hoặc đơn vị: kiểm tra ngay tại công thức, biểu phí hoặc trang nguồn. Nếu wiki trộn tiếng Việt và tiếng Anh, dùng tiếng Việt tự nhiên nhưng giữ mã loại lệnh (LO, MO, MTL, MAK) khi WS/WA cần phân biệt; giải thích mã khi viết cho khách.
