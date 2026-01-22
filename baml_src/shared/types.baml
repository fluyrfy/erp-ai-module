// ===============================
// Shared Types (Reusable)
// ===============================

// 顯示共用
class SummaryMeta {
  title string @description("A short, 3-5 word title describing this thinking step.")
  description string @description("Detailed explanation")
}
// 決策類共用
class DecisionMetadata {
  summary SummaryMeta @description("Detailed rationale for why this decision was made")
  confidence float @description("Confidence level 0.0-1.0")
}

// 洞察類共用
class InsightMetadata {
  // === 摘要 === 
  summary SummaryMeta @description("Human-readable summary of what was discovered")

  // === 身份描述 === 
  // 決定要載入哪個分析模組
  data_type string @description("Domain classification in snake_case")
  // 狀態機判斷
  result_status string @description("'SUCCESS', 'NO_DATA', 'PARTIAL', or 'ERROR'")
  // LLM 閱讀的簡報
  content_description string @description("Contextual summary of what this data represents (Time range, Target Department, Filters applied).")
  
  // === 洞察內容 ===
  // 做邏輯推理用的素材
  key_points string[] @description("factual observations")
  // 關鍵數據（含單位）
  metrics map<string, string> @description("Keys with unit suffix")
  // 關鍵關連 ID
  extracted_entities map<string, string[]> @description("Entity IDs for chaining")
}

class NarrativeMetadata {
  answer string @description(#"
    Natural language answer for user.
    Should be a complete, readable paragraph
    Include context, numbers, and actionable info naturally.
  "#)
  data_attachment DataAttachment?
}

class DataAttachment {
  format string @description(#"
    The fundamental structural category of the information.
    Derived from the logical topology and dimensionality of the raw data.
    Acts as a high-level hint for the rendering engine to select the appropriate visualization container.
  "#)
  content string @description(#"
    The raw, render-ready payload.
    FORMATTING PROTOCOL:
    - For syntax-sensitive formats (e.g., Mermaid, PlantUML), content MUST be wrapped in markdown code fences with language tag.
    - Use ASCII-safe identifiers for node/class names; non-ASCII text should be placed in label syntax (e.g., ["顯示名稱"]).
    - Avoid empty structural bodies or redundant syntax.
    - For unstructured archetypes, return raw text.
  "#)
}