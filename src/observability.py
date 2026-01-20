"""
OpenTelemetry setup - 只在 main.py import 一次
"""

import os
from typing import Sequence
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExportResult,
    SpanExporter,  # 開發時用，印在 console
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from baml_client import config


class JsonFileExporter(SpanExporter):
    """
    自定義 Exporter：將 Spans 以 NDJSON (Line-delimited JSON) 格式寫入檔案
    每一行都是一個完整的 JSON 物件
    """

    def __init__(self, output_file: str = "traces.json"):
        self.output_file = output_file
        # 確保檔案存在或清空舊檔案（依需求決定是否要 append）
        # 這裡示範 append 模式，重啟程式不會清空舊 log
        # 如果希望每次重啟都清空，可以用 "w" 模式開一次檔案再關閉
        pass

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            with open(self.output_file, "a", encoding="utf-8") as f:
                for span in spans:
                    # span.to_json() 會回傳 JSON 字串
                    # 預設格式包含了 name, context, kind, start_time, end_time, attributes 等
                    f.write(span.to_json() + "\n")
            return SpanExportResult.SUCCESS
        except Exception as e:
            print(f"Failed to export traces to json: {e}")
            return SpanExportResult.FAILURE

    def shutdown(self):
        pass


def setup_tracing(service_name: str = "erp-ai-module"):
    """
    初始化 OpenTelemetry (只需呼叫一次)

    Args:
        service_name: 你的服務名稱
    """

    # 1. 設定 Resource (標記這個服務的身份)
    resource = Resource.create(
        {
            "service.name": service_name,
        }
    )

    # 2. 建立 TracerProvider
    provider = TracerProvider(resource=resource)

    # 3. 加入 Exporter (開發階段用 Console，生產用 OTLP)
    # if config.ENV == "development":
    # 開發時：直接印在 terminal
    # console_exporter = ConsoleSpanExporter()
    os.makedirs("logs", exist_ok=True)

    json_exporter = JsonFileExporter(output_file="logs/traces.json")
    provider.add_span_processor(BatchSpanProcessor(json_exporter))
    # else:
    #     # 生產時：送到 Jaeger/Grafana Tempo
    #     from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    #         OTLPSpanExporter,
    #     )

    #     otlp_exporter = OTLPSpanExporter(
    #         endpoint="http://jaeger:4317",  # 你的 Jaeger endpoint
    #         insecure=True,
    #     )
    #     provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # 4. 設為全域 Tracer
    trace.set_tracer_provider(provider)

    # 5. 自動 instrument httpx (你的 HTTP 請求會自動被追蹤)
    HTTPXClientInstrumentor().instrument()

    print(f"✅ OpenTelemetry initialized for service: {service_name}")
