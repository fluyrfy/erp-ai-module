// ===============================
// Shared Types (Reusable)
// ===============================

// 決策類共用
class DecisionMetadata {
  action string @description("A short, 3-5 word title describing this thinking step.")
  confidence float @description("Confidence level 0.0-1.0")
  reason string @description("Detailed rationale for why this decision was made")
}

// 洞察類共用
class InsightMetadata {
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
  // 增加 'mermaid', 'code' 等類型，讓前端決定渲染器
  format string @description("Visual format: 'markdown_table', 'mermaid_flowchart', 'mermaid_class', 'mermaid_sequence', 'list', 'code_block'")
  content string @description("The raw markdown or code content")
  record_count int? @description("Optional count if applicable")
}