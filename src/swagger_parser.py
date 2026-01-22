"""
Swagger/OpenAPI parser - 從後端動態載入並瘦身
"""

import json
import httpx
from typing import Any, Dict, List

import urllib

from src.config import config


class SwaggerParser:
    def __init__(self, module_name: str):
        """
        Args:
            module_name: e.g. "hr", "inventory" (Parser 會自己去 Config 找 URL)
        """
        self.module_name = module_name
        self.swagger_url = SwaggerParser.build_doc_url(module_name)
        self._raw: dict | None = None
        self._catalog: list[dict] | None = None

    @staticmethod
    def build_doc_url(module_name: str) -> str:
        """
        根據 Config 自動組裝 Swagger URL
        Example: "http://localhost:8080/v3/api-docs/hr"
        """
        base = config.BACKEND_BASE_URL.rstrip("/")
        doc_path = config.SWAGGER_DOC_PATH.rstrip("/")
        return f"{base}{doc_path}/{module_name}"

    @staticmethod
    def build_config_url() -> str:
        """
        組裝 Service Discovery URL
        Example: "http://localhost:8080/v3/api-docs/swagger-config"
        """
        base = config.BACKEND_BASE_URL.rstrip("/")
        doc_path = config.SWAGGER_DOC_PATH.rstrip("/")
        return f"{base}{doc_path}/swagger-config"

    # 服務發現 (Service Discovery)
    @staticmethod
    async def fetch_available_modules() -> List[Dict[str, str]]:
        """
        [Service Discovery] 呼叫 swagger-config 取得所有可用的模組清單
        """
        target_url = SwaggerParser.build_config_url()
        # print(f"[SwaggerParser] 🔍 Discovering modules from: {target_url}")

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(target_url)
                if response.status_code == 200:
                    data = response.json()
                    modules = []
                    # 標準化回傳: [{'name': 'hr', 'url': 'http://.../v3/api-docs/hr'}]
                    for u in data.get("urls", []):
                        name = u.get("name")
                        rel_url = u.get("url")
                        if name and rel_url:
                            # 這裡我們甚至可以忽略後端給的 url，自己用 build_doc_url 重組確保一致
                            # 但為了相容性，我們先用後端的，並補全 domain
                            full_url = (
                                rel_url
                                if rel_url.startswith("http")
                                else f"{config.BACKEND_BASE_URL.rstrip('/')}{rel_url}"
                            )
                            modules.append({"name": name, "url": full_url})
                    return modules
        except Exception as e:
            print(f"⚠️ Service Discovery Error: {e}")
        return []

    @staticmethod
    async def fetch_module_detail(name: str, url: str) -> dict | None:
        """
        下載並解析單一模組的 Swagger JSON，回傳清洗後的物件
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    print(f"⚠️ Failed to fetch {name}: {resp.status_code}")
                    return None

                data = resp.json()

                # 1. 抓取我們在 Java Config 寫好的 Info (Title & Description)
                info = data.get("info", {})
                clean_title = info.get("title", "")
                clean_desc = info.get("description", "")

                # 2. 抓取 Tags 作為 Capabilities
                # 這會對應到 Java 的 tags: [{name: "職稱管理", ...}]
                tags = data.get("tags", [])
                capabilities = [t.get("name") for t in tags if t.get("name")]

                # 3. 回傳結構化資料 (這就是 AI 要吃的 JSON Object)
                return {
                    "module": name,  # 給程式路由用 (key)
                    "title": clean_title,  # 給 AI 理解用 (human readable name)
                    "description": clean_desc,  # 給 AI 理解用 (summary)
                    "capabilities": capabilities,  # 給 AI 判斷功能用
                }

        except Exception as e:
            print(f"⚠️ Error parsing module {name}: {e}")
            return None

    @staticmethod
    async def fetch_module_metadata(name: str, url: str) -> str:
        """
        [Lightweight Fetch] 給 L2 用。只抓 Info 和 Tags，不解析詳細 Schema。
        """
        parsed = urllib.parse.urlparse(url)
        encoded_path = urllib.parse.quote(parsed.path, safe="/:")
        safe_url = parsed._replace(path=encoded_path).geturl()

        print(f"[DEBUG] Fetching: {safe_url}")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return f"Module: {name} (Status: {resp.status_code})"

                spec = resp.json()
                info = spec.get("info", {})
                title = info.get("title", name)
                desc = info.get("description", "")
                tags = spec.get("tags", [])

                summary = [f"Module: {name} ({title})"]
                if desc:
                    summary.append(f"Description: {desc}")

                if tags:
                    summary.append("Capabilities (Controllers):")
                    for tag in tags:
                        t_name = tag.get("name")
                        t_desc = tag.get("description", "")
                        if t_name:
                            summary.append(f"  - {t_name}: {t_desc}")

                return "\n".join(summary)
        except Exception as e:
            return f"Module: {name} (Offline: {e})"

    async def load(self) -> None:
        """從後端載入 Swagger JSON"""
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_S) as client:
            resp = await client.get(self.swagger_url)
            resp.raise_for_status()
            self._raw = resp.json()
        self._catalog = self._parse_to_catalog(self._raw)

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

                # 提取 Response Schema
                response_schema = self._parse_response(spec.get("responses"), swagger)

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
                            spec.get("requestBody"), swagger
                        ),
                        "response": response_schema,
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
        """解析 request body schema (支援巢狀輸入)"""
        if not body:
            return None

        content = body.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})

        # 這樣就算是輸入參數有巢狀物件 (例如 List<DTO>)，也能完整展開給 LLM 看
        resolved_schema = self._deep_resolve(schema, swagger, seen_refs=set())
        # --- 關鍵過濾：移除 pageNum 和 pageSize ---
        properties = resolved_schema.get("properties", {})
        filtered_properties = {
            k: v for k, v in properties.items() if k not in ["pageNum", "pageSize"]
        }
        resolved_schema["properties"] = filtered_properties
        required = resolved_schema.get("required", [])
        filtered_required = [r for r in required if r not in ["pageNum", "pageSize"]]
        resolved_schema["required"] = filtered_required

        return {
            "required": body.get("required", False),
            "schema": resolved_schema,
            "properties": filtered_properties,
            "required_fields": filtered_required,  # 注意：required 通常在 schema 內層
        }

    def _deep_resolve(self, schema: dict, swagger: dict, seen_refs: set) -> dict:
        """
        新增 seen_refs 參數，記錄走過的路徑。
        遇到已存在的 ref 直接回傳描述，防止無窮迴圈 (針對部門樹狀結構)。
        """
        # 1. 處理 $ref
        if "$ref" in schema:
            ref_path = schema["$ref"]

            # 防護網：如果 ref 已經出現過，停止展開
            if ref_path in seen_refs:
                ref_name = ref_path.split("/")[-1]
                return {
                    "type": "object",
                    "description": f"[Recursive] 循環引用至 {ref_name}，已停止展開。",
                }

            # 加入路徑記錄
            new_seen = seen_refs.copy()
            new_seen.add(ref_path)

            resolved = self._resolve_ref(ref_path, swagger)
            # 傳遞 new_seen 給下一層
            return self._deep_resolve(resolved, swagger, seen_refs=new_seen)

        # 2. 處理 Array (items)
        if schema.get("type") == "array" and "items" in schema:
            new_schema = schema.copy()
            # 傳遞 seen_refs
            new_schema["items"] = self._deep_resolve(
                schema["items"], swagger, seen_refs
            )
            return new_schema

        # 3. 處理 Object (properties)
        if "properties" in schema:
            new_schema = schema.copy()
            new_props = {}
            for k, v in schema["properties"].items():
                # 傳遞 seen_refs
                new_props[k] = self._deep_resolve(v, swagger, seen_refs)
            new_schema["properties"] = new_props
            return new_schema

        # 4. 處理 allOf
        if "allOf" in schema:
            merged = {}
            for item in schema["allOf"]:
                # 傳遞 seen_refs
                resolved_item = self._deep_resolve(item, swagger, seen_refs)
                if "properties" in resolved_item:
                    merged.update(resolved_item["properties"])
            return {"type": "object", "properties": merged}

        return schema

    def _parse_response(self, responses: dict | None, swagger: dict) -> dict | None:
        if not responses:
            return None

        target_schema = None

        for code, resp in responses.items():
            content = resp.get("content", {})
            media_type = content.get("application/json") or content.get("*/*")

            if media_type and "schema" in media_type:
                target_schema = media_type["schema"]
                break

        if not target_schema:
            return None

        # 啟動時傳入空的集合 set()
        return self._deep_resolve(target_schema, swagger, seen_refs=set())

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
                    lines.append(f"  - {p['name']}{req} ({p['in']}, {p['type']})")

            # 顯示 Request Body 結構
            if api["request_body"]:
                lines.append("- Request Body:")
                props = api["request_body"].get("properties", {})
                for key, val in props.items():
                    desc = val.get("description", "")
                    lines.append(f"  - {key}: {val.get('type')} ({desc})")

            # 顯示 Response 結構 (這是解決問題的關鍵！)
            if api["response"]:
                lines.append("- Response Output:")
                # 將 dictionary 轉成簡化的 JSON 字串顯示
                json_str = json.dumps(api["response"], ensure_ascii=False, indent=2)
                lines.append(f"```json\n{json_str}\n```")

            lines.append("")

        return "\n".join(lines)

    def get_api_by_id(self, api_id: str) -> dict | None:
        """取得單一 API spec（給 Step 2 用）"""
        if not self._catalog:
            return None
        return next((a for a in self._catalog if a["id"] == api_id), None)
