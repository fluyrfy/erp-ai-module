"""
Swagger/OpenAPI parser - 從後端動態載入並瘦身
"""

import httpx
from typing import Any


class SwaggerParser:
    def __init__(self, swagger_url: str):
        """
        Args:
            swagger_url: e.g. "https://your-backend/v3/api-docs"
        """
        self.swagger_url = swagger_url
        self._raw: dict | None = None
        self._catalog: list[dict] | None = None

    async def load(self) -> None:
        """從後端載入 Swagger JSON"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(self.swagger_url)
            resp.raise_for_status()
            self._raw = resp.json()
        self._catalog = self._parse_to_catalog(self._raw, self._raw)

    def _resolve_ref(self, ref: str, swagger: dict) -> dict:
        """簡單 $ref 解析（支援 #/components/schemas/XXX）"""
        if not ref.startswith("#/"):
            return {"type": "object"}  # fallback
        parts = ref.split("/", 3)
        if len(parts) != 4 or parts[1] != "components":
            return {"type": "object"}
        component_type = parts[2]
        component_name = parts[3]
        return (
            swagger.get("components", {})
            .get(component_type, {})
            .get(component_name, {})
        )

    def _parse_to_catalog(self, swagger: dict) -> list[dict]:
        """瘦身：只保留 LLM 需要的欄位"""
        catalog = []

        for path, methods in swagger.get("paths", {}).items():
            for method, spec in methods.items():
                if method not in ["get", "post", "put", "delete", "patch"]:
                    continue

                catalog.append(
                    {
                        "id": spec.get("operationId", f"{method.upper()} {path}"),
                        "method": method.upper(),
                        "path": path,
                        "summary": spec.get("summary", ""),
                        "description": spec.get("description", ""),
                        "tags": spec.get("tags", []),
                        "parameters": self._parse_parameters(
                            spec.get("parameters", [])
                        ),
                        "request_body": self._parse_request_body(
                            spec.get("requestBody")
                        ),
                    }
                )

        return catalog

    def _parse_parameters(self, params: list) -> list[dict]:
        """解析參數，只保留關鍵資訊"""
        return [
            {
                "name": p.get("name"),
                "in": p.get("in"),  # query, path, header
                "required": p.get("required", False),
                "type": p.get("schema", {}).get("type", "string"),
                "description": p.get("description", ""),
            }
            for p in params
        ]

    def _parse_request_body(self, body: dict | None, swagger: dict) -> dict | None:
        """解析 request body schema"""
        if not body:
            return None

        content = body.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})

        if "$ref" in schema:
            resolved = self._resolve_ref(schema["$ref"], swagger)
            schema = resolved if resolved else schema
        elif "allOf" in schema:
            # 簡單處理 allOf（常見於繼承）
            merged = {}
            for item in schema["allOf"]:
                if "$ref" in item:
                    merged.update(self._resolve_ref(item["$ref"], swagger))
            schema = merged

        return {
            "required": body.get("required", False),
            "schema": schema,  # 可以進一步簡化
            "properties": schema.get("properties", {}),  # 直接給 LLM 看欄位
            "required_fields": schema.get("required", []),
        }

    def get_catalog_text(self) -> str:
        """輸出給 LLM 的純文字格式"""
        if not self._catalog:
            return ""

        lines = []
        for api in self._catalog:
            lines.append(f"### {api['id']}")
            lines.append(f"- Method: {api['method']}")
            lines.append(f"- Path: {api['path']}")
            lines.append(f"- Summary: {api['summary']}")

            if api["parameters"]:
                lines.append("- Parameters:")
                for p in api["parameters"]:
                    req = "*" if p["required"] else ""
                    lines.append(
                        f"  - {p['name']}{req} ({p['in']}, {p['type']}): {p['description']}"
                    )

            lines.append("")

        return "\n".join(lines)

    def get_api_by_id(self, api_id: str) -> dict | None:
        """取得單一 API spec（給 Step 2 用）"""
        if not self._catalog:
            return None
        return next((a for a in self._catalog if a["id"] == api_id), None)
