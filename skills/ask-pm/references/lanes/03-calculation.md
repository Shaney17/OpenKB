# Nhánh 3 — Phép tính, phí, lãi và số tiền

Mục tiêu là giúp WS/WA hiểu công thức và biết còn thiếu dữ liệu gì, không tạo một con số có vẻ chính thức từ trí nhớ mô hình.

## Tìm quy tắc

Tìm theo tên khoản mục, “cách tính”, “công thức”, “làm tròn” (thử tiếng Anh nếu cần). Đọc toàn văn các trang compiled liên quan. Wiki OpenKB là Markdown tự do; không tìm các field inputs[], output_unit hoặc calculate_formula của hệ cũ. Công thức phải hiện rõ trong trang đọc được. Một câu mô tả chung không đủ để suy công thức cụ thể.

Đối chiếu các trang mô tả cùng khoản mục. Nếu công thức hoặc điều kiện khác nhau trong cùng phạm vi, CONFLICT; không chọn theo score hay thời điểm sửa tài liệu. Nếu cùng công thức nhưng khác phạm vi, nêu điều kiện chọn.

## Tính có kiểm soát

1. Viết công thức đúng theo tài liệu, dẫn wikilink trang chứa nó.
2. Liệt kê mọi đầu vào và nguồn của chúng. Phân biệt số khách cung cấp, số WS/WA cần tra trong chi tiết giao dịch, và tỷ lệ/cấu hình cần có nguồn chính thức. Không hỏi WS/WA đoán một tỷ lệ mà họ không tra được.
3. Vẽ cây phụ thuộc nếu kết quả của phép tính này là đầu vào của phép tính khác. Giữ nguyên thứ tự và mọi lần làm tròn trung gian; không gộp các phép nhân khi tài liệu làm tròn ở giữa.
4. Xác định đơn vị cho từng đại lượng và quy tắc đổi tỷ lệ phần trăm. Không mặc định VND, chữ số thập phân, ngưỡng hoặc cách làm tròn.
5. Thiếu bất kỳ đầu vào bắt buộc nào: NEED_MORE_INPUT. Giải thích cơ chế và hỏi một lần tất cả dữ liệu thiếu, kèm gợi ý nơi WS/WA có thể lấy nếu tài liệu chỉ ra. Không xuất con số cụ thể.
6. Nếu đủ, thế số từng dòng, ghi giá trị trung gian và kết quả. Dùng công cụ tính đáng tin nếu môi trường có; vẫn kiểm tra đơn vị và làm tròn. Ghi rõ đây là số tự tính cần đối chiếu trước khi gửi khách.

Không có công thức trong trang compiled: KNOWLEDGE_GAP hoặc PM_REVIEW_REQUIRED nếu chỉ thấy source thô. Không dùng công thức “thông thường” của ngành.

## Khi khách báo số khác

Đừng kết luận hệ thống sai từ phép tính minh họa. So sánh đúng kỳ, loại lệnh, chiều giao dịch, vai trò maker/taker, tỷ lệ thực tế, phần đã thu/tạm giữ và quy tắc làm tròn mà wiki có nêu. Chuyển nhánh 4 để phân loại chênh lệch; nhánh 5 chỉ khi đã có hiện tượng cần báo kiểm tra.

Phần 2 chỉ có kết quả số khi nó đã VERIFIED theo toàn bộ điều kiện và số đã được đối chiếu phù hợp. Nếu chưa, giải thích cần xác minh gì, không cho khách một mức phí ước lượng giả chính thức.
