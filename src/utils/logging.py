"""
Logging utilities with decorators + OpenTelemetry integration
"""

import functools
import inspect
import json
from pathlib import Path
from typing import Any, Callable, TypeVar
from loguru import logger
from opentelemetry import trace

# 移除預設 handler
logger.remove()

# 加入檔案 handler（自動輪轉）
logger.add(
    "logs/app_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
    encoding="utf-8",
)

# 加入 console handler（開發時用）
logger.add(
    lambda msg: print(msg, end=""),
    level="DEBUG",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
)

T = TypeVar("T")

# 取得 tracer
tracer = trace.get_tracer(__name__)


def traced(
    _func: Callable[..., T] | None = None,
    *,
    span_name: str | None = None,
    log_input: bool = True,
    log_output: bool = True,
    max_length: int = 500,
    capture_exception: bool = True,
    record_output_to_span: bool = True,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    裝飾器：同時處理 Logging + OpenTelemetry Tracing

    Args:
        span_name: Span 名稱（預設用函數名）
        log_input: 是否記錄輸入參數
        log_output: 是否記錄輸出結果
        max_length: 單一參數/回傳值的最大記錄長度
        capture_exception: 是否在 span 中記錄 exception
         record_output_to_span: 是否將 output 記錄到 span attributes

    Example:
        @traced()
        async def my_function(a: int, b: str) -> dict:
            return {"result": a + len(b)}
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # 決定 span 名稱
        actual_span_name = span_name or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            # 建立 span
            with tracer.start_as_current_span(actual_span_name) as span:
                func_name = f"{func.__module__}.{func.__qualname__}"

                # Log 輸入
                if log_input:
                    sig = inspect.signature(func)
                    bound_args = sig.bind(*args, **kwargs)
                    bound_args.apply_defaults()

                    params_log = {}
                    for name, value in bound_args.arguments.items():
                        params_log[name] = _truncate_value(value, max_length)

                    logger.debug(
                        f"[CALL] {func_name} | params={json.dumps(params_log, ensure_ascii=False, default=str)}"
                    )

                    # 也記錄到 span
                    span.set_attribute("function.name", func_name)
                    span.set_attribute(
                        "function.params",
                        json.dumps(params_log, ensure_ascii=False, default=str)[:500],
                    )

                # 執行函數
                try:
                    result = func(*args, **kwargs)

                    # Log 輸出
                    if log_output:
                        result_log = _truncate_value(result, max_length)
                        logger.debug(
                            f"[RETURN] {func_name} | result={json.dumps(result_log, ensure_ascii=False, default=str)}"
                        )

                        # 記錄到 span
                        span.set_attribute(
                            "function.result_type", type(result).__name__
                        )

                        if record_output_to_span:
                            _record_to_span(span, result)

                    return result

                except Exception as e:
                    logger.exception(
                        f"[ERROR] {func_name} | {type(e).__name__}: {str(e)}"
                    )

                    # 記錄到 span
                    if capture_exception:
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                        span.record_exception(e)

                    raise

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            # 建立 span
            with tracer.start_as_current_span(actual_span_name) as span:
                func_name = f"{func.__module__}.{func.__qualname__}"

                # Log 輸入
                if log_input:
                    sig = inspect.signature(func)
                    bound_args = sig.bind(*args, **kwargs)
                    bound_args.apply_defaults()

                    params_log = {}
                    for name, value in bound_args.arguments.items():
                        params_log[name] = _truncate_value(value, max_length)

                    logger.debug(
                        f"[CALL] {func_name} | params={json.dumps(params_log, ensure_ascii=False, default=str)}"
                    )

                    # 也記錄到 span
                    span.set_attribute("function.name", func_name)
                    span.set_attribute(
                        "function.params",
                        json.dumps(params_log, ensure_ascii=False, default=str)[:500],
                    )

                # 執行函數
                try:
                    result = await func(*args, **kwargs)

                    # Log 輸出
                    if log_output:
                        result_log = _truncate_value(result, max_length)
                        logger.debug(
                            f"[RETURN] {func_name} | result={json.dumps(result_log, ensure_ascii=False, default=str)}"
                        )

                        # 記錄到 span
                        span.set_attribute(
                            "function.result_type", type(result).__name__
                        )

                        if record_output_to_span:
                            _record_to_span(span, result)

                    return result

                except Exception as e:
                    logger.exception(
                        f"[ERROR] {func_name} | {type(e).__name__}: {str(e)}"
                    )

                    # 記錄到 span
                    if capture_exception:
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                        span.record_exception(e)

                    raise

        @functools.wraps(func)
        async def async_generator_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(actual_span_name) as span:
                func_name = f"{func.__module__}.{func.__qualname__}"

                # Log 輸入
                if log_input:
                    sig = inspect.signature(func)
                    bound_args = sig.bind(*args, **kwargs)
                    bound_args.apply_defaults()

                    params_log = {}
                    for name, value in bound_args.arguments.items():
                        params_log[name] = _truncate_value(value, max_length)

                    logger.debug(
                        f"[CALL] {func_name} | params={json.dumps(params_log, ensure_ascii=False, default=str)}"
                    )
                    span.set_attribute("function.name", func_name)
                    span.set_attribute(
                        "function.params",
                        json.dumps(params_log, ensure_ascii=False, default=str)[:500],
                    )

                # 執行 async generator
                try:
                    yield_count = 0
                    async for item in func(*args, **kwargs):
                        yield_count += 1
                        yield item

                    # 完成後記錄
                    if log_output:
                        logger.debug(
                            f"[RETURN] {func_name} | yielded {yield_count} items"
                        )
                        span.set_attribute("function.yield_count", yield_count)

                except Exception as e:
                    logger.exception(
                        f"[ERROR] {func_name} | {type(e).__name__}: {str(e)}"
                    )
                    if capture_exception:
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                        span.record_exception(e)
                    raise

        # 根據函數類型返回對應的 wrapper
        if inspect.isasyncgenfunction(func):
            return async_generator_wrapper  # async generator
        elif inspect.iscoroutinefunction(func):
            return async_wrapper  # async function
        else:
            return sync_wrapper  # sync function

    if _func is None:
        return decorator
    else:
        return decorator(_func)


def _truncate_value(value: Any, max_length: int) -> Any:
    """截斷過長的值（保持原樣）"""
    if isinstance(value, str):
        if len(value) > max_length:
            return value[:max_length] + f"... (truncated, total {len(value)} chars)"
        return value

    elif isinstance(value, (list, tuple)):
        if len(value) > 10:
            return [_truncate_value(v, max_length) for v in value[:10]] + [
                f"... ({len(value)} items)"
            ]
        return [_truncate_value(v, max_length) for v in value]

    elif isinstance(value, dict):
        if len(value) > 10:
            keys = list(value.keys())[:10]
            truncated = {k: _truncate_value(value[k], max_length) for k in keys}
            truncated["_truncated"] = f"... ({len(value)} keys)"
            return truncated
        return {k: _truncate_value(v, max_length) for k, v in value.items()}

    else:
        str_repr = str(value)
        if len(str_repr) > max_length:
            return str_repr[:max_length] + f"... (truncated)"
        return value


def _record_to_span(span, result):
    """將 Output 寫入 Span 的邏輯"""
    try:
        if isinstance(result, (str, int, float, bool)):
            span.set_attribute("function.output", str(result)[:1000])
        elif isinstance(result, dict):
            # 這裡簡單處理，你也可以加上 json.dumps
            span.set_attribute("function.output", str(result)[:2000])
            if "success" in result:
                span.set_attribute("result.success", result["success"])
        elif hasattr(result, "model_dump"):  # Pydantic v2
            span.set_attribute("function.output", str(result.model_dump())[:2000])
        elif hasattr(result, "dict"):  # Pydantic v1
            span.set_attribute("function.output", str(result.dict())[:2000])
        elif isinstance(result, (list, tuple)):
            span.set_attribute("function.output_length", len(result))
            span.set_attribute("function.output_preview", str(result[:5])[:500])
        else:
            span.set_attribute("function.output", str(result)[:500])
    except Exception:
        pass
