# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Nhật Thắng
- **MSSV:** 2A202602727
- **Lớp:** K4-L3B
- **Repository URL:**
- **Commit SHA cuối:**
- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-2A202602727`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (20/21 bản ghi thiếu trường bắt buộc và enrichment, 0 correlation ID) | 100/100 | Baseline chưa làm TODO CP1 nên thấp là bình thường |
| `validate_dashboard.py` | 6/6 panel hợp lệ | | |
| `pytest` | 22 passed | 24 passed | Python 3.11.9, chạy ở thư mục gốc |
| Số traces hợp lệ | 10 request load test, `/health` báo `tracing_enabled: true` (chưa xác nhận trên Langfuse) | | Prompt `day13-chat` chưa tạo nên app dùng prompt fallback (404) |
| Số PII leak | 0 | 0 | Đo trên log mới sau khi chuyển log cũ ra ngoài repo |
| Latency P95 / TTFT P95 | 1356ms (request đầu tiên khởi tạo chậm) / 50ms | P95 155ms / TTFT 50ms lúc khỏe; P95 2652ms khi có incident | Chưa vượt SLO 3000ms nhưng lệch ~17 lần so với baseline | |
| Retrieval success rate | 100% | 100% | Sự cố rag_slow làm chậm chứ không làm lỗi nên tỷ lệ không đổi | |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` (`app/middleware.py`) gọi `clear_contextvars()` đầu mỗi request để không rò context giữa các request, rồi lấy header `x-request-id` nếu client gửi, nếu không thì sinh `req-<8 hex>` bằng `uuid4`. ID được `bind_contextvars` nên mọi dòng log trong request tự có `correlation_id`, được lưu vào `request.state.correlation_id` để truyền cho agent (đưa vào metadata trace), và được trả về qua header `x-request-id` cùng `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `ts`, `level`, `service`, `event`, `correlation_id`, và các trường enrichment `user_id_hash` (SHA-256 cắt 12 ký tự, không log user_id thô), `session_id`, `feature`, `model`, `env`, bind trong `app/main.py` trước log `request_received`. Log `response_sent` thêm `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`.
- **Cách bảo đảm PII được scrub trước khi ghi:** đăng ký processor `scrub_event` trong `configure_logging()` ngay trước `JsonlFileProcessor` và `JSONRenderer`, nên dữ liệu đã được che trước khi ghi file hoặc render JSON. Processor che các chuỗi trong `payload` và `event` bằng `scrub_text` (pattern email, điện thoại VN, CCCD, thẻ thanh toán → `[REDACTED_<LOẠI>]`). Preview của message/answer còn được che thêm bằng `summarize_text`. Lưu ý: cơ chế này chỉ bảo vệ log và trace, không che dữ liệu gửi vào LLM.
- **Cách kiểm chứng kết quả:** chuyển log baseline ra ngoài repo (`..\logs-cp0-baseline.jsonl`), restart API, chạy `load_test.py` rồi `validate_logs.py` (100/100, 0 PII leak). Gửi thủ công một request chứa email/số điện thoại/CCCD/thẻ giả, xác nhận log chỉ có `[REDACTED_*]`, response header có `x-request-id` đúng định dạng và header `x-request-id` do client gửi được giữ nguyên. Thêm test CCCD và thẻ trong `tests/test_pii.py`; `pytest` 24 passed. Evidence: `evidence/04-structured-log.png`, `evidence/05-pii-redaction.png`.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Dùng key của project `day13-k4-l3b-2A202602727` trong `.env`, tự chạy `load_test.py` và các request thử; trong Langfuse lọc `isRootObservation:true` thấy các trace `day13-agent-request`, mỗi trace có `correlation_id` khớp với log trong `data/logs.jsonl`. Evidence: `evidence/06-trace-list.png`.
- **Cấu trúc root/retrieval/generation observations:** `lab-agent-run` (agent, root) → `retrieval` (loại retriever, metadata `doc_count`) và `llm-generation` (loại generation, có model, `usage_details` input/output, `cost_details`, `ttft_ms`). Không capture raw input/output (`capture_input=False`, `capture_output=False`) để tránh PII. Evidence: `evidence/07-trace-waterfall.png`.
- **Cách nối trace với log:** `correlation_id` được bind vào log (middleware) và đưa vào metadata của trace qua `propagate_attributes`; tìm trace bằng cùng `correlation_id` với dòng log. Evidence: `evidence/08-trace-metadata.png`.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** version 1, labels `baseline` và `production`
- **Version/label candidate:** version 2, label `candidate` (thêm dòng "Answer concisely.")
- **Trace ID của mỗi version:** v1 (`req-prompt-v1`, label baseline, `prompt_version` 1, `tokens_in` 28): `2ee2421770cf322f382ec514755cb8a9`; v2 (`req-prompt-v2`, label candidate, `prompt_version` 2, `tokens_in` 32): `19165f275ebadbbb049a4bfb3f8465b7`
- **Cách promote và rollback `production`:**

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** Dựng bằng `scripts/build_dashboard.py` (HTML tự chứa, không cần thư viện ngoài) từ `data/logs.jsonl` theo `config/dashboard.yaml`, cửa sổ 60 phút, tự tải lại 30 giây. Sáu panel: Latency (P50/P95/P99 + TTFT), Traffic, Errors (error rate + retrieval success), Cost, Tokens, Quality; mỗi panel có đơn vị và đường threshold. Evidence: `evidence/11-dashboard-overview.png`, `evidence/12-incident-metric.png`.
- **SLO và lý do chọn:** `fast_successful_requests`: 99.5% request `response_sent` có `latency_ms <= 3000` trong 28 ngày. Baseline P95 khoảng 155ms (request đầu tiên 1356–1800ms do khởi tạo), nên ngưỡng 3000ms đủ rộng cho dao động bình thường nhưng vẫn bắt được sự cố retrieval chậm thêm 2.5s.
- **Cách tính error budget:** SLO 99.5% trong 28 ngày nghĩa là error budget 0.5%. Với 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn 3000ms.
- **Ba alert và runbook tương ứng:** `HighLatencyP95` (warning, P95 > 3000ms trong 5 phút, `docs/alerts.md#alert-1`), `HighErrorRate` (critical, error rate > 2% trong 5 phút, `#alert-2`), `LowQualityOrRetrievalSuccess` (warning, quality < 0.75 hoặc retrieval success < 90% trong 10 phút, `#alert-3`). Tất cả gửi Slack `#k4-l3b-alerts`, owner `student-2A202602727`, runbook theo Metrics → Logs → Traces + mitigation.

> Ví dụ cách viết error budget: "SLO 99.5% trong 28 ngày nghĩa là error budget 0.5%. Nếu workload có 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn ngưỡng SLO."

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Khoảng thời gian điều tra:** 2026-09-30 04:04:38–04:04:49 UTC (baseline 10 request lúc 04:04:30 UTC, sau đó bật incident và chạy `load_test.py --challenge --concurrency 5`)
- **Triệu chứng từ metrics:** Latency (từ `latency_ms` trong log) tăng từ P50 152ms ở baseline lên khoảng 2652ms ở cả 5 request challenge (tăng ~2.5s). Các panel khác không đổi: TTFT P95 vẫn 50ms, error rate 0%, quality 0.84–0.88, token và cost mỗi request tương đương baseline. Như vậy chỉ có latency bất thường, và không phải do LLM (TTFT giữ nguyên).
- **Log line và correlation ID liên quan:** `response_sent` với `correlation_id=req-ee2d3d81`, `latency_ms=2653`, `ttft_ms=50`, `feature=monitoring`, `tool_success=true` (ts 2026-09-30T04:04:46.513Z).
- **Trace ID và span gây ảnh hưởng:** Trace `0856b02c495faadeddf5a8b07519e911` (cùng `correlation_id`): `lab-agent-run` 2.654s, trong đó span `retrieval` 2.501s còn `llm-generation` chỉ 0.152s. Span `retrieval` chiếm gần như toàn bộ thời gian.
- **Root cause:** Bước retrieval (vector store/RAG) bị chậm thêm khoảng 2.5s (kịch bản `rag_slow`). LLM generation vẫn bình thường (TTFT 50ms, 152ms), request không lỗi nên error rate không đổi; chỉ latency tăng.
- **Fix action:** Tắt incident bằng `python scripts/inject_incident.py --disable` (`/health` báo cả 3 incident đều false). Chạy lại `load_test.py`: latency về 151–152ms, đã hồi phục.
- **Preventive measure:** Alert `HighLatencyP95` (P95 > 3000ms trong 5 phút, hiện 2.6s chưa vượt nên nên hạ ngưỡng cảnh báo sớm hoặc thêm alert riêng cho latency retrieval), thêm timeout và fallback cho retrieval, ghi latency riêng của bước retrieval vào log để dashboard chỉ ra bước chậm mà không cần mở trace, và runbook Alert 1 đã có bước so sánh span `retrieval` và `llm-generation`.

> Gợi ý cách viết ngắn, không thay cho evidence thực tế: "Metric cho thấy `[latency/error/cost/quality]` bất thường trong `[khoảng thời gian]`. Log line `[event]` có `correlation_id=[...]` đại diện cho request bị ảnh hưởng. Trace cùng `correlation_id` cho thấy span `[retrieval/generation/prompt/tool]` có dấu hiệu `[chậm/lỗi/token tăng]`. Root cause là `[nguyên nhân suy ra từ evidence]`. Fix action là `[hành động khôi phục]`; preventive measure là `[alert/runbook/test/guardrail để ngăn tái diễn]`."

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Đặt `@observe` trực tiếp trên `retrieve` và `FakeLLM.generate` (thay vì bọc trong agent) để có span con `retrieval` và `llm-generation`, kèm `capture_input/output=False` để không đưa PII vào trace; correlation_id đi cùng metadata để nối log với trace.
- **Một lỗi/blocker đã gặp:** Máy không có Python 3.12 và `uv`; lần `pip install` đầu bị lỗi mạng `IncompleteRead`. Ngoài ra Langfuse trả 404 vì prompt `day13-chat` (label `production`) chưa được tạo.
- **Cách tìm nguyên nhân và xử lý:** Dùng Python 3.11.9 (nằm trong khoảng 3.11–3.13 cho phép) và chạy lại pip với `--retries 10 --timeout 60`. Với lỗi 404, log API cho thấy app tự dùng prompt fallback nên vẫn chạy; prompt sẽ được tạo trên Langfuse ở CP2.
- **Cách hiểu luồng Metrics → Logs → Traces:** Metrics cho biết có vấn đề và từ lúc nào (latency tăng, các chỉ số khác giữ nguyên); log giúp chọn đúng một request qua `correlation_id`; trace cho thấy bước nào gây ra (retrieval 2.5s, generation vẫn 0.15s). Mỗi lớp thu hẹp phạm vi, không phải đoán.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** Prompt version cho biết mỗi request dùng prompt nào (v2 có `tokens_in` 32 so với 28 của v1), nên khi có regression có thể đổi label `production` về version cũ mà không sửa code. Token/cost và SLO biến chất lượng vận hành thành số đo và ngân sách lỗi để đặt alert.
- **Điều quan trọng nhất đã học:** Quan sát hệ thống LLM cần ba lớp bổ sung nhau (metrics, logs, traces) nối với nhau bằng một `correlation_id`, và dữ liệu nhạy cảm phải được che trước khi ghi log/trace.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** Cơ chế che PII chỉ áp dụng cho log và trace, không che dữ liệu gửi vào LLM. Dashboard là công cụ tự viết (HTML tĩnh), không phải Grafana. Latency sự cố (2.65s) chưa vượt ngưỡng alert 3000ms nên cần hạ ngưỡng hoặc thêm alert riêng cho retrieval.

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
