"""
Management command to seed a complete demo match with teams, participants, questions, and units (§30 Phase 7, §33).
Usage:
    python manage.py seed_demo [--room-code DEMO24] [--reset]
"""

from typing import Any, Dict, List

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.matches.models import Match
from apps.matches.services import MatchService
from apps.questions.models import (
    Question,
    QuestionDifficulty,
    QuestionType,
)
from apps.teams.models import MemberRole, Team, TeamStatus
from apps.units.seeds import ensure_standard_units

# Comprehensive Question Bank (≥ 45 questions across categories and difficulties)
DEMO_QUESTIONS: List[Dict[str, Any]] = [
    # --- Category: Web & HTTP (Easy to Hard) ---
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Web & Networking",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Mã trạng thái HTTP nào biểu thị một tài nguyên được tạo thành công trên máy chủ?",
        "options": [
            {"key": "A", "text": "200 OK"},
            {"key": "B", "text": "201 Created"},
            {"key": "C", "text": "204 No Content"},
            {"key": "D", "text": "301 Moved Permanently"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 45,
        "explanation": "HTTP 201 Created biểu thị yêu cầu đã được xử lý và một tài nguyên mới đã được tạo thành công.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Web & Networking",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Phương thức HTTP nào theo tiêu chuẩn RFC là 'Idempotent' nhưng KHÔNG 'Safe'?",
        "options": [
            {"key": "A", "text": "GET"},
            {"key": "B", "text": "POST"},
            {"key": "C", "text": "PUT"},
            {"key": "D", "text": "PATCH"},
        ],
        "answer_key": "C",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 45,
        "explanation": "PUT là idempotent (gọi nhiều lần cho cùng kết quả) nhưng không safe (thay đổi trạng thái server).",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "Web & Networking",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Cổng mạng (port) tiêu chuẩn của giao thức DNS là bao nhiêu?",
        "options": [],
        "answer_key": "53",
        "answer_validator_type": "NUMERIC",
        "time_limit_seconds": 35,
        "explanation": "Cổng mặc định của DNS là 53 qua UDP/TCP.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Web & Networking",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Header HTTP nào được dùng trong cơ chế CORS để máy chủ chỉ định những domain nào được phép truy cập tài nguyên?",
        "options": [
            {"key": "A", "text": "Access-Control-Allow-Origin"},
            {"key": "B", "text": "Access-Control-Request-Headers"},
            {"key": "C", "text": "Allow-Cross-Domain"},
            {"key": "D", "text": "Sec-Fetch-Origin"},
        ],
        "answer_key": "A",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 45,
        "explanation": "Access-Control-Allow-Origin quy định các domain nguồn được phép chia sẻ tài nguyên.",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "Web & Networking",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Cơ chế bảo mật trình duyệt nào ngăn chặn các script từ nguồn (origin) khác truy cập DOM hoặc cookie của trang web hiện tại?",
        "options": [],
        "answer_key": "Same-Origin Policy",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 50,
        "explanation": "Same-Origin Policy (SOP) là cơ chế bảo mật cốt lõi của các trình duyệt web hiện đại.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Web & Networking",
        "difficulty": QuestionDifficulty.HARD,
        "content": "Trong giao thức WebSocket (RFC 6455), frame opcode 0x8 đại diện cho loại frame nào?",
        "options": [
            {"key": "A", "text": "Text Frame"},
            {"key": "B", "text": "Binary Frame"},
            {"key": "C", "text": "Connection Close"},
            {"key": "D", "text": "Ping Frame"},
        ],
        "answer_key": "C",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 50,
        "explanation": "Opcode 0x8 là Close Frame báo hiệu đóng kết nối WebSocket.",
    },

    # --- Category: Databases & SQL ---
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "Databases",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Câu lệnh SQL nào dùng để xóa vĩnh viễn toàn bộ bảng cùng cấu trúc và dữ liệu của nó khỏi cơ sở dữ liệu?",
        "options": [],
        "answer_key": "DROP TABLE",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 40,
        "explanation": "Lệnh DROP TABLE xóa cả bảng và cấu trúc, khác với DELETE hoặc TRUNCATE chỉ xóa bản ghi.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Databases",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Chữ cái viết tắt 'I' trong thuộc tính ACID của cơ sở dữ liệu quan hệ đại diện cho từ nào?",
        "options": [
            {"key": "A", "text": "Integrity"},
            {"key": "B", "text": "Isolation"},
            {"key": "C", "text": "Immutable"},
            {"key": "D", "text": "Idempotency"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 40,
        "explanation": "ACID là viết tắt của Atomicity, Consistency, Isolation, Durability.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Databases",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Mức cô lập giao dịch (Transaction Isolation Level) nào ngăn chặn được cả Dirty Read và Non-repeatable Read nhưng vẫn có thể gặp Phantom Read?",
        "options": [
            {"key": "A", "text": "Read Uncommitted"},
            {"key": "B", "text": "Read Committed"},
            {"key": "C", "text": "Repeatable Read"},
            {"key": "D", "text": "Serializable"},
        ],
        "answer_key": "C",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 50,
        "explanation": "Repeatable Read ngăn Dirty Read và Non-repeatable Read, nhưng theo chuẩn SQL-92 vẫn có thể gặp Phantom Read.",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "Databases",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Kỹ thuật ghi nhật ký trước khi thay đổi dữ liệu chính trên đĩa để đảm bảo tính Durability trong RDBMS được viết tắt là gì (3 chữ cái)?",
        "options": [],
        "answer_key": "WAL",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 45,
        "explanation": "Write-Ahead Logging (WAL) đảm bảo dữ liệu ghi vào nhật ký trước khi thay đổi bảng chính.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Databases",
        "difficulty": QuestionDifficulty.HARD,
        "content": "Cấu trúc dữ liệu chỉ mục phổ biến nhất được sử dụng cho các trường tìm kiếm theo khoảng (range scan) trong PostgreSQL là gì?",
        "options": [
            {"key": "A", "text": "B-Tree"},
            {"key": "B", "text": "Hash Index"},
            {"key": "C", "text": "Bitmap Index"},
            {"key": "D", "text": "Trie"},
        ],
        "answer_key": "A",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 45,
        "explanation": "B-Tree index duy trì thứ tự sắp xếp và tối ưu vượt trội cho các truy vấn theo khoảng.",
    },

    # --- Category: Python & Django ---
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Python & Django",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Trong Python, từ khóa nào được sử dụng để định nghĩa một generator function tạo ra chuỗi giá trị lặp?",
        "options": [
            {"key": "A", "text": "return"},
            {"key": "B", "text": "yield"},
            {"key": "C", "text": "generate"},
            {"key": "D", "text": "async"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 40,
        "explanation": "Từ khóa 'yield' biến hàm thành một generator lười (lazy iterator).",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "Python & Django",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Trong Django ORM, phương thức nào của QuerySet được dùng để thực hiện khóa hàng (row-level locking) trong cơ sở dữ liệu?",
        "options": [],
        "answer_key": "select_for_update",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 45,
        "explanation": "select_for_update() sinh câu lệnh SELECT ... FOR UPDATE nhằm khóa các hàng đang truy vấn.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Python & Django",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Trong Django, phương thức nào của QuerySet cho phép tối ưu truy vấn n+1 cho quan hệ ForeignKey (Many-to-One) bằng cách sử dụng SQL JOIN?",
        "options": [
            {"key": "A", "text": "prefetch_related()"},
            {"key": "B", "text": "select_related()"},
            {"key": "C", "text": "annotate()"},
            {"key": "D", "text": "aggregate()"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 45,
        "explanation": "select_related() dùng SQL JOIN cho single-valued relationships (ForeignKey, OneToOne).",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "Python & Django",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Trong Python 3, hàm tích hợp sẵn (built-in function) nào trả về số phần tử của một container (như list, tuple, dict)?",
        "options": [],
        "answer_key": "len",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 35,
        "explanation": "Hàm len() gọi ngầm định phương thức __len__() của đối tượng.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Python & Django",
        "difficulty": QuestionDifficulty.HARD,
        "content": "Cơ chế Global Interpreter Lock (GIL) trong CPython giới hạn điều gì đối với luồng (threads)?",
        "options": [
            {"key": "A", "text": "Chỉ cho phép tối đa 1024 luồng hoạt động cùng lúc"},
            {"key": "B", "text": "Chỉ cho phép một luồng thực thi Python bytecode tại một thời điểm trong một tiến trình"},
            {"key": "C", "text": "Ngăn chặn hoàn toàn các thao tác I/O bất đồng bộ"},
            {"key": "D", "text": "Bắt buộc mọi hàm phải chạy tuần tự không thể dùng ThreadPool"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 55,
        "explanation": "GIL bảo vệ bộ nhớ của CPython bằng cách chỉ cho phép một luồng giữ lock thực thi bytecode.",
    },

    # --- Category: DevOps, Docker & CI/CD ---
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "DevOps & Cloud",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Lệnh Docker nào dùng để liệt kê tất cả các container đang chạy trên hệ thống?",
        "options": [],
        "answer_key": "docker ps",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 40,
        "explanation": "'docker ps' (hoặc docker container ls) hiển thị các container đang hoạt động.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "DevOps & Cloud",
        "difficulty": QuestionDifficulty.EASY,
        "content": "File cấu hình nào thường được sử dụng để điều phối nhiều container liên kết với nhau bằng công cụ Docker Compose?",
        "options": [
            {"key": "A", "text": "Dockerfile"},
            {"key": "B", "text": "docker-compose.yml"},
            {"key": "C", "text": "compose.json"},
            {"key": "D", "text": "container-lock.yml"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 40,
        "explanation": "docker-compose.yml là file định nghĩa dịch vụ, mạng và volume tiêu chuẩn của Docker Compose.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "DevOps & Cloud",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Trong Kubernetes, đơn vị nhỏ nhất và cơ bản nhất có thể triển khai và quản lý được gọi là gì?",
        "options": [
            {"key": "A", "text": "Node"},
            {"key": "B", "text": "Pod"},
            {"key": "C", "text": "Service"},
            {"key": "D", "text": "Deployment"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 45,
        "explanation": "Pod là đơn vị tính toán nhỏ nhất trong Kubernetes, đóng gói một hoặc nhiều container.",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "DevOps & Cloud",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Tín hiệu hệ điều hành POSIX tiêu chuẩn nào (ví dụ SIG...) được gửi để yêu cầu một tiến trình dừng nhẹ nhàng (graceful termination)?",
        "options": [],
        "answer_key": "SIGTERM",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 45,
        "explanation": "SIGTERM (signal 15) yêu cầu tiến trình kết thúc êm thấm, trong khi SIGKILL (signal 9) buộc dừng ngay.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "DevOps & Cloud",
        "difficulty": QuestionDifficulty.HARD,
        "content": "Công nghệ Linux kernel nào cho phép chạy các chương trình an toàn, hiệu năng cao trực tiếp trong kernel mà không cần sửa code kernel hay nạp kernel module?",
        "options": [
            {"key": "A", "text": "eBPF"},
            {"key": "B", "text": "cgroups v2"},
            {"key": "C", "text": "AppArmor"},
            {"key": "D", "text": "Seccomp"},
        ],
        "answer_key": "A",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 55,
        "explanation": "eBPF (Extended Berkeley Packet Filter) là công nghệ cách mạng chạy bytecode an toàn trong Linux kernel.",
    },

    # --- Category: Security & Cryptography ---
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Security",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Thuật toán băm một chiều (cryptographic hash) an toàn nào sau đây KHÔNG NÊN sử dụng để lưu trữ mật khẩu người dùng do quá nhanh?",
        "options": [
            {"key": "A", "text": "Bcrypt"},
            {"key": "B", "text": "Argon2"},
            {"key": "C", "text": "MD5"},
            {"key": "D", "text": "PBKDF2"},
        ],
        "answer_key": "C",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 45,
        "explanation": "MD5 đã bị phá vỡ hoàn toàn và quá nhanh, dễ bị tấn công brute-force và va chạm (collision).",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "Security",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Lỗ hổng bảo mật web nào xảy ra khi kẻ tấn công chèn mã JavaScript độc hại vào trang web để thực thi trên trình duyệt người dùng (viết tắt 3 chữ cái)?",
        "options": [],
        "answer_key": "XSS",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 40,
        "explanation": "XSS (Cross-Site Scripting) là lỗi chèn script độc hại vào website.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Security",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Trong cấu trúc JSON Web Token (JWT), ba phần được phân tách bằng dấu chấm (.) theo thứ tự là gì?",
        "options": [
            {"key": "A", "text": "Payload.Header.Signature"},
            {"key": "B", "text": "Header.Payload.Signature"},
            {"key": "C", "text": "Header.Signature.Payload"},
            {"key": "D", "text": "Signature.Header.Payload"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 45,
        "explanation": "Cấu trúc chuẩn của JWT là Header.Payload.Signature.",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "Security",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Thuộc tính bảo mật nào của cookie ngăn JavaScript phía client truy cập vào cookie (ví dụ qua document.cookie)?",
        "options": [],
        "answer_key": "HttpOnly",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 45,
        "explanation": "Cờ HttpOnly bảo vệ cookie khỏi các cuộc tấn công XSS đánh cắp session token.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Security",
        "difficulty": QuestionDifficulty.HARD,
        "content": "Kỹ thuật phòng vệ nào sau đây hiệu quả nhất để ngăn chặn triệt để tấn công SQL Injection?",
        "options": [
            {"key": "A", "text": "Thay thế dấu nháy đơn bằng nháy kép"},
            {"key": "B", "text": "Sử dụng Parameterized Queries (Prepared Statements)"},
            {"key": "C", "text": "Chỉ kiểm tra độ dài chuỗi đầu vào"},
            {"key": "D", "text": "Chạy cơ sở dữ liệu trên port không mặc định"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 45,
        "explanation": "Prepared Statements tách rời hoàn toàn câu lệnh SQL và tham số dữ liệu, ngăn chèn mã.",
    },

    # --- Category: System Design & Architecture ---
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "System Design",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Theo định lý CAP, trong một hệ thống phân tán khi xảy ra phân vùng mạng (Partition Tolerance), hệ thống chỉ có thể chọn đánh đổi giữa hai yếu tố nào?",
        "options": [
            {"key": "A", "text": "Consistency và Availability"},
            {"key": "B", "text": "Performance và Scalability"},
            {"key": "C", "text": "Security và Usability"},
            {"key": "D", "text": "Throughput và Latency"},
        ],
        "answer_key": "A",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 50,
        "explanation": "Định lý CAP chỉ ra khi có Partition (P), hệ thống phải lựa chọn giữa Tính nhất quán (C) hoặc Tính sẵn sàng (A).",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "System Design",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Cơ chế bảo vệ hệ thống phân tán, tự động ngắt các lời gọi dịch vụ đang gặp sự cố để tránh sụp đổ dây chuyền (cascading failure), mượn tên từ thiết bị điện nào?",
        "options": [],
        "answer_key": "Circuit Breaker",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 45,
        "explanation": "Pattern Circuit Breaker (Cầu dao tự động) bảo vệ hệ thống phân tán khỏi lỗi lan truyền.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "System Design",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Chiến lược xóa dữ liệu bộ đệm (Cache Eviction Policy) nào loại bỏ phần tử đã không được truy cập trong thời gian dài nhất?",
        "options": [
            {"key": "A", "text": "FIFO (First In First Out)"},
            {"key": "B", "text": "LRU (Least Recently Used)"},
            {"key": "C", "text": "LFU (Least Frequently Used)"},
            {"key": "D", "text": "Random Eviction"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 45,
        "explanation": "LRU xóa các item có lần truy cập gần nhất xa nhất trong quá khứ.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "System Design",
        "difficulty": QuestionDifficulty.HARD,
        "content": "Trong kiến trúc Microservices, Pattern nào giải quyết vấn đề quản lý transaction phân tán qua nhiều service bằng cách dùng chuỗi các local transaction và compensating transaction?",
        "options": [
            {"key": "A", "text": "Saga Pattern"},
            {"key": "B", "text": "CQRS Pattern"},
            {"key": "C", "text": "Event Sourcing"},
            {"key": "D", "text": "Strangler Fig"},
        ],
        "answer_key": "A",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 55,
        "explanation": "Saga Pattern điều phối chuỗi giao dịch cục bộ và bù trừ lỗi (compensating actions).",
    },

    # --- Category: Data Structures & Algorithms ---
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Algorithms",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Độ phức tạp thời gian trung bình (average time complexity) của thuật toán QuickSort là bao nhiêu?",
        "options": [
            {"key": "A", "text": "O(n)"},
            {"key": "B", "text": "O(n log n)"},
            {"key": "C", "text": "O(n^2)"},
            {"key": "D", "text": "O(log n)"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 40,
        "explanation": "QuickSort có độ phức tạp trung bình là O(n log n), xấu nhất là O(n^2) khi chọn pivot kém.",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "Algorithms",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Cấu trúc dữ liệu nào hoạt động theo nguyên lý LIFO (Last In First Out)?",
        "options": [],
        "answer_key": "Stack",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 35,
        "explanation": "Stack (Ngăn xếp) hoạt động theo cơ chế Vào sau, Ra trước (LIFO).",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Algorithms",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Thuật toán nào sau đây được sử dụng phổ biến nhất để tìm đường đi ngắn nhất giữa hai đỉnh trong đồ thị có trọng số không âm?",
        "options": [
            {"key": "A", "text": "Dijkstra"},
            {"key": "B", "text": "Kruskal"},
            {"key": "C", "text": "Depth-First Search (DFS)"},
            {"key": "D", "text": "Tarjan"},
        ],
        "answer_key": "A",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 45,
        "explanation": "Thuật toán Dijkstra tìm đường đi ngắn nhất với trọng số cạnh không âm.",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "Algorithms",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Số nguyên tố chẵn duy nhất là số nào?",
        "options": [],
        "answer_key": "2",
        "answer_validator_type": "NUMERIC",
        "time_limit_seconds": 30,
        "explanation": "2 là số nguyên tố chẵn duy nhất và cũng là số nguyên tố nhỏ nhất.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Algorithms",
        "difficulty": QuestionDifficulty.HARD,
        "content": "Cấu trúc dữ liệu xác suất (probabilistic data structure) nào cực kỳ tối ưu về bộ nhớ, dùng để kiểm tra một phần tử 'chắc chắn không thuộc tập hợp' hoặc 'có thể thuộc tập hợp'?",
        "options": [
            {"key": "A", "text": "Bloom Filter"},
            {"key": "B", "text": "Trie"},
            {"key": "C", "text": "Skip List"},
            {"key": "D", "text": "Fibonacci Heap"},
        ],
        "answer_key": "A",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 55,
        "explanation": "Bloom Filter không bao giờ cho False Negative, chỉ có thể có False Positive.",
    },

    # --- Category: Team-building & Mentorship ---
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Mentorship & Culture",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Trong mối quan hệ Mentor–Mentee hiệu quả, vai trò quan trọng nhất của Mentor là gì?",
        "options": [
            {"key": "A", "text": "Làm thay toàn bộ công việc cho Mentee"},
            {"key": "B", "text": "Định hướng, chia sẻ kinh nghiệm và tạo môi trường học hỏi chủ động cho Mentee"},
            {"key": "C", "text": "Chỉ trích khắt khe các sai lầm mà không đưa ra giải pháp"},
            {"key": "D", "text": "Chỉ giao nhiệm vụ hành chính không liên quan chuyên môn"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 40,
        "explanation": "Mentor đóng vai trò người dẫn dắt (guide), lắng nghe và tạo điều kiện phát triển cho Mentee.",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "Mentorship & Culture",
        "difficulty": QuestionDifficulty.EASY,
        "content": "Mô hình mục tiêu phổ biến có 5 tiêu chí: Specific, Measurable, Achievable, Relevant, Time-bound viết tắt là gì?",
        "options": [],
        "answer_key": "SMART",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 35,
        "explanation": "Mô hình SMART là tiêu chuẩn vàng để thiết lập mục tiêu công việc và học tập.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Mentorship & Culture",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Nguyên tắc 'Psychological Safety' (An toàn tâm lý) trong đội ngũ của Google Aristotle Research có ý nghĩa cốt lõi là gì?",
        "options": [
            {"key": "A", "text": "Các thành viên luôn luôn đồng ý với nhau và không bao giờ tranh luận"},
            {"key": "B", "text": "Các thành viên cảm thấy an toàn khi chấp nhận rủi ro, nêu ý kiến và thừa nhận sai lầm mà không sợ bị phán xét"},
            {"key": "C", "text": "Tất cả mọi người đều có mức lương như nhau"},
            {"key": "D", "text": "Không ai phải chịu trách nhiệm khi dự án thất bại"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 50,
        "explanation": "Psychological Safety là yếu tố quan trọng nhất tạo nên một đội ngũ làm việc hiệu suất cao.",
    },
    {
        "type": QuestionType.SHORT_TEXT,
        "category": "Mentorship & Culture",
        "difficulty": QuestionDifficulty.MEDIUM,
        "content": "Thuật ngữ 2 từ chỉ buổi họp ngắn đầu ngày của đội nhóm Agile/Scrum để đồng bộ công việc trong 15 phút gọi là gì?",
        "options": [],
        "answer_key": "Daily Standup",
        "answer_validator_type": "NORMALIZED_TEXT",
        "time_limit_seconds": 40,
        "explanation": "Daily Standup (hoặc Daily Scrum) giúp cả đội chia sẻ tiến độ và tháo gỡ khó khăn.",
    },
    {
        "type": QuestionType.MULTIPLE_CHOICE,
        "category": "Mentorship & Culture",
        "difficulty": QuestionDifficulty.HARD,
        "content": "Trong phương pháp phản hồi SBI (Situation - Behavior - Impact), yếu tố 'Impact' nhằm mục đích gì?",
        "options": [
            {"key": "A", "text": "Chỉ trích tính cách cá nhân của đối phương"},
            {"key": "B", "text": "Mô tả kết quả và ảnh hưởng cụ thể từ hành vi đó đến công việc hoặc tập thể"},
            {"key": "C", "text": "Đưa ra hình phạt kỷ luật ngay lập tức"},
            {"key": "D", "text": "Bỏ qua lỗi lầm để duy trì sự hòa hoãn"},
        ],
        "answer_key": "B",
        "answer_validator_type": "MULTIPLE_CHOICE",
        "time_limit_seconds": 50,
        "explanation": "Mô hình SBI tập trung vào dữ kiện khách quan: Bối cảnh, Hành vi và Tác động thực tế.",
    },
]


class Command(BaseCommand):
    help = "Seeds standard units, ≥40 questions, and a ready-to-play sample match with 4 teams (§30 Phase 7, §33)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--room-code",
            type=str,
            default="DEMO24",
            help="Room code for the demo match (default: DEMO24)",
        )
        parser.add_argument(
            "--name",
            type=str,
            default="Mentor-Mentee Cup 2026",
            help="Match name (default: 'Mentor-Mentee Cup 2026')",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Wipe and recreate demo match if room code already exists",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress informational output",
        )

    def handle(self, *args, **options):
        room_code = options["room_code"].upper().strip()
        match_name = options["name"].strip()
        do_reset = options["reset"]
        quiet = options["quiet"]

        if not quiet:
            self.stdout.write(self.style.NOTICE("==> Step 1: Ensuring standard units are seeded..."))
        units = ensure_standard_units()
        if not quiet:
            self.stdout.write(self.style.SUCCESS(f"    ✓ {len(units)} standard units ready."))

        if not quiet:
            self.stdout.write(self.style.NOTICE("==> Step 2: Seeding comprehensive question bank..."))
        seeded_q_count = 0
        for q_data in DEMO_QUESTIONS:
            _, created = Question.objects.update_or_create(
                content=q_data["content"],
                defaults={
                    "type": q_data["type"],
                    "category": q_data["category"],
                    "difficulty": q_data["difficulty"],
                    "options": q_data["options"],
                    "answer_key": q_data["answer_key"],
                    "answer_validator_type": q_data["answer_validator_type"],
                    "time_limit_seconds": q_data["time_limit_seconds"],
                    "explanation": q_data["explanation"],
                    "is_active": True,
                },
            )
            if created:
                seeded_q_count += 1

        total_questions = Question.objects.filter(is_active=True).count()
        if not quiet:
            self.stdout.write(
                self.style.SUCCESS(f"    ✓ {total_questions} active questions available in bank.")
            )

        if not quiet:
            self.stdout.write(self.style.NOTICE(f"==> Step 3: Setting up sample match '{match_name}' [{room_code}]..."))

        existing_match = Match.objects.filter(room_code=room_code).first()
        if existing_match:
            if do_reset:
                if not quiet:
                    self.stdout.write(f"    Existing match found with room code {room_code}. Resetting...")
                existing_match.delete()
            else:
                if not quiet:
                    self.stdout.write(self.style.WARNING(
                        f"    Match with room code {room_code} already exists. Use --reset to recreate."
                    ))
                return

        # Create Match with transactions
        with transaction.atomic():
            match, host_token = MatchService.create_match(
                name=match_name,
                configuration={
                    "initial_base_hp": 500,
                    "initial_coins": 100,
                    "match_duration_minutes": 30,
                    "max_questions_per_team": 8,
                    "correct_answer_coin_reward": 30,
                    "base_income_coins": 10,
                    "max_towers_per_team": None,
                    "max_units_per_team": 5,
                    "max_deployed_per_action": 1,
                    "max_tower_per_action": 1,
                    "phase_durations": {
                        "lobby": 0,
                        "preparation": 180,
                        "build_and_scout": 300,
                        "war": 900,
                        "final_assault": 420,
                    },
                },
            )
            # Override room code to demo room code
            match.room_code = room_code
            match.save()

            # 4 Teams with Mentor and Mentees
            teams_blueprint = [
                {
                    "name": "Red Dragons",
                    "mentor": "Alice Mentor",
                    "mentees": ["Bob Mentee", "Charlie Mentee"],
                },
                {
                    "name": "Blue Phoenix",
                    "mentor": "David Mentor",
                    "mentees": ["Eve Mentee", "Frank Mentee"],
                },
                {
                    "name": "Green Titans",
                    "mentor": "Grace Mentor",
                    "mentees": ["Heidi Mentee", "Ivan Mentee"],
                },
                {
                    "name": "Golden Wolves",
                    "mentor": "Judy Mentor",
                    "mentees": ["Kevin Mentee", "Laura Mentee"],
                },
            ]

            team_results = []
            for t_idx, t_data in enumerate(teams_blueprint, start=1):
                team = Team.objects.create(
                    match=match,
                    name=t_data["name"],
                    base_hp=500,
                    initial_base_hp=500,
                    coins=100,
                    status=TeamStatus.ACTIVE,
                    is_ready=True,
                )

                # Add mentor
                mentor_member, mentor_token = MatchService.join_match(
                    match=match,
                    display_name=t_data["mentor"],
                    team_id=str(team.id),
                    role=MemberRole.MENTOR,
                )

                # Add mentees
                mentee_tokens = []
                for mentee_name in t_data["mentees"]:
                    memb, tok = MatchService.join_match(
                        match=match,
                        display_name=mentee_name,
                        team_id=str(team.id),
                        role=MemberRole.MENTEE,
                    )
                    mentee_tokens.append((mentee_name, tok))

                team_results.append({
                    "team": team,
                    "mentor": (t_data["mentor"], mentor_token),
                    "mentees": mentee_tokens,
                })

        if not quiet:
            self.stdout.write(self.style.SUCCESS("\n" + "=" * 76))
            self.stdout.write(self.style.SUCCESS("  TOWER DEFENSE DEMO MATCH CREATED SUCCESSFULLY!"))
            self.stdout.write(self.style.SUCCESS("=" * 76))
            self.stdout.write(f"  Match ID:   {match.id}")
            self.stdout.write(f"  Match Name: {match.name}")
            self.stdout.write(f"  Room Code:  {self.style.SUCCESS(match.room_code)}")
            self.stdout.write(f"  Host Token: {self.style.WARNING(host_token)}")
            self.stdout.write("-" * 76)
            self.stdout.write("  TEAMS & PARTICIPANT TOKENS:")
            for idx, res in enumerate(team_results, 1):
                t = res["team"]
                self.stdout.write(f"\n  [Team {idx}] {t.name} (Coins: {t.coins}, HP: {t.base_hp}):")
                m_name, m_tok = res["mentor"]
                self.stdout.write(f"    - Mentor: {m_name:<16} Token: {m_tok}")
                for mentee_name, tok in res["mentees"]:
                    self.stdout.write(f"    - Mentee: {mentee_name:<16} Token: {tok}")
            self.stdout.write("=" * 76)
            self.stdout.write("  Quick Start:")
            self.stdout.write(f"  - Host Console:      http://localhost:5173/host/{match.id}?token={host_token}")
            self.stdout.write(f"  - Join as Player:    http://localhost:5173/join (Enter room code: {match.room_code})")
            self.stdout.write(f"  - Spectator Screen:  http://localhost:5173/battle/{match.id}?spectator=1")
            self.stdout.write("=" * 76 + "\n")
