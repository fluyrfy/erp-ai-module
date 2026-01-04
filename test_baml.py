import os
from dotenv import load_dotenv

# 載入 .env
load_dotenv()

# 確認 API key 有載入
print(f"API Key loaded: {os.getenv('OPENAI_API_KEY')[:10]}...")

# 測試 BAML
from baml_client import b
from baml_client.types import Resume

result = b.ExtractResume(
    """
    王小明
    wang.xiaoming@example.com
    
    經歷：
    - 2020-2023 ABC公司 軟體工程師
    - 2018-2020 XYZ公司 實習生
    
    技能：
    - Python
    - JavaScript
    - SQL
"""
)

print(f"姓名: {result.name}")
print(f"Email: {result.email}")
print(f"經歷: {result.experience}")
print(f"技能: {result.skills}")
