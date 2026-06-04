"""UI Constants — Centralized UI text and greetings for cypher result formatters."""

MEDICAL_DISCLAIMER = (
    "\n\n> [!WARNING]\n"
    "> **Lưu ý y khoa:** Các thông tin trên chỉ mang tính chất tham khảo dựa trên Knowledge Graph. "
    "Vui lòng thăm khám trực tiếp với bác sĩ chuyên khoa để có chẩn đoán và phác đồ điều trị chính xác nhất."
)

GREETINGS_SYMPTOMS = [
    "Dưới đây là thông tin về triệu chứng của **{label}** mà bạn đang tìm kiếm:",
    "Theo cơ sở dữ liệu y khoa, **{label}** có các biểu hiện sau:",
    "Gửi bạn chi tiết các triệu chứng của **{label}**:",
    "Chào bạn, tôi đã tìm thấy các dấu hiệu nhận biết của **{label}**:"
]

GREETINGS_MEDICINE = [
    "Đây là danh sách thuốc thường được chỉ định cho **{label}**:",
    "Đối với **{label}**, các bác sĩ thường kê đơn các loại thuốc sau:",
    "Thông tin về thuốc điều trị **{label}**:"
]

GREETINGS_TREATMENT = [
    "Dưới đây là các phương pháp điều trị cho **{label}**:",
    "Theo phác đồ phổ biến, **{label}** có thể được điều trị như sau:",
    "Chi tiết về hướng điều trị **{label}**:"
]

GREETINGS_ADVICE = [
    "Dưới đây là lời khuyên dinh dưỡng và sinh hoạt cho **{label}**:",
    "Để hỗ trợ điều trị **{label}**, bạn nên tham khảo chế độ sau:",
    "Chế độ ăn uống và sinh hoạt gợi ý cho **{label}**:"
]

GREETINGS_PREVENTION = [
    "Để phòng tránh **{label}**, bạn nên áp dụng các biện pháp sau:",
    "Thông tin về cách phòng ngừa **{label}**:",
    "Dưới đây là một số cách giúp bạn ngăn ngừa **{label}**:"
]

GREETINGS_DEPARTMENT = [
    "Để khám và điều trị **{label}**, bạn nên đến:",
    "Khoa chuyên môn phụ trách **{label}** là:"
]

GREETINGS_PROFILE = [
    "Dưới đây là hồ sơ tổng quan về **{label}**:",
    "Thông tin toàn diện về **{label}**:"
]

GREETINGS_LINKED = [
    "Bên cạnh đó, **{label}** có liên quan tới các bệnh lý sau:",
    "Các bệnh lý có mối liên hệ với **{label}**:"
]

GREETINGS_FIND_BY_SYMPTOM = [
    "Dựa trên triệu chứng **{label}**, đây là một số bệnh lý có thể mắc phải:",
    "Các bệnh lý có biểu hiện **{label}** bao gồm:"
]

GREETINGS_FIND_BY_MEDICINE = [
    "Thuốc **{label}** thường được dùng để điều trị các bệnh sau:",
    "Chỉ định phổ biến của **{label}** bao gồm:"
]

GREETINGS_FIND_BY_NUTRITION_AVOID = [
    "Các bệnh lý nên kiêng **{label}** bao gồm:",
    "Bạn nên hạn chế **{label}** nếu đang mắc các bệnh sau:"
]

GREETINGS_FIND_BY_NUTRITION_EAT = [
    "Thực phẩm **{label}** rất tốt cho các bệnh lý sau:",
    "Các bệnh nên bổ sung **{label}** bao gồm:"
]

GREETINGS_FIND_BY_PREVENTION = [
    "Biện pháp **{label}** giúp phòng ngừa các bệnh sau:",
    "Các bệnh có thể ngăn ngừa bằng cách **{label}**:"
]
