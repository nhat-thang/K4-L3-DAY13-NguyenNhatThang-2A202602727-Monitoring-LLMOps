# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: SLO `fast_successful_requests` (latency `response_sent` <= 3000ms, target 99.5%/28 ngày)
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` liên tục 5 phút
- Ảnh hưởng tới người dùng: người dùng chờ lâu hơn trước khi nhận câu trả lời, error budget bị tiêu nhanh
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Latency, xác nhận P95/P99 và TTFT vượt ngưỡng từ lúc nào.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh span `retrieval` và `llm-generation` để xem bước nào chậm.
- Mitigation tạm thời: nếu `retrieval` chậm thì tắt incident `rag_slow` hoặc chuyển sang nguồn dự phòng; nếu `llm-generation` chậm hoặc token tăng sau khi đổi prompt thì rollback label `production` về version cũ; giảm tải khi demo.
- Owner: `student-2A202602727`

## Alert 2

- Tên: `HighErrorRate`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: SLO `fast_successful_requests` và guardrail `error_rate_pct_max: 2`
- Điều kiện và thời gian duy trì: `count(request_failed) / count(request_received) * 100 > 2` liên tục 5 phút
- Ảnh hưởng tới người dùng: request trả HTTP 500, người dùng không nhận được câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Errors, xem error rate và `count_by(error_type)` để biết loại lỗi chiếm đa số.
  2. Lọc log `event == "request_failed"`, lấy `correlation_id` và `error_type` của một request lỗi.
  3. Mở trace cùng `correlation_id`, tìm span có level ERROR (thường là `retrieval`) và đọc status message.
- Mitigation tạm thời: tắt incident `tool_fail` nếu đang bật, khôi phục kết nối vector store/cấu hình retrieval, rollback thay đổi gần nhất.
- Owner: `student-2A202602727`

## Alert 3

- Tên: `LowQualityOrRetrievalSuccess`
- Severity: `warning`
- Duration: `10m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: guardrails `quality_score_avg_min: 0.75` và `retrieval_success_rate_pct_min: 90`
- Điều kiện và thời gian duy trì: `mean(quality_score) < 0.75` hoặc retrieval success (`tool_success == true` trên mọi event có field này) `< 90%` liên tục 10 phút
- Ảnh hưởng tới người dùng: câu trả lời kém chất lượng hoặc thiếu ngữ cảnh dù request vẫn thành công, khó thấy qua error rate
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Quality và Errors (retrieval success), xác nhận chỉ số nào giảm và từ lúc nào.
  2. Lọc log có `quality_score` thấp hoặc `tool_success == false`, lấy `correlation_id`.
  3. Mở trace cùng `correlation_id`, kiểm tra metadata `doc_count`, `prompt_version` và span `retrieval`.
- Mitigation tạm thời: rollback prompt `production` về version trước nếu regression bắt đầu sau khi đổi prompt; kiểm tra và khôi phục nguồn tài liệu retrieval.
- Owner: `student-2A202602727`
