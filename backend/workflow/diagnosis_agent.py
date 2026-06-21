"""
诊断Agent — 阶段3: 综合推理 + 输出
输入: collected_info + search_results
输出: DiagnosisResult (primary_diagnosis, differential_diagnosis, risk_assessment,
      recommendations, red_flags, references, disclaimer)
"""
from __future__ import annotations

import logging
import os

from config.settings import Settings
from llm.real_llm_adapter import RealLLMAdapter, LLMAPIError, LLMRateLimitError, LLMTimeoutError

logger = logging.getLogger(__name__)
settings = Settings()
_adapter: RealLLMAdapter | None = None


def _get_adapter() -> RealLLMAdapter:
    global _adapter
    if _adapter is None:
        _adapter = RealLLMAdapter()
    return _adapter


class DiagnosisAgent:
    def __init__(self) -> None:
        self.adapter = _get_adapter()

    async def generate(self, collected_info: dict, search_results: list,
                       messages: list, disclaimer: str) -> str:
        chief = collected_info.get("patient_info", {}).get("chief_complaint", "未指定症状")
        logger.info("DiagnosisAgent: chief=%s collected_keys=%s", chief, list(collected_info.keys()))

        try:
            knowledge = ""
            if search_results:
                fragments = [r.get("content", "")[:300] for r in search_results[:3] if isinstance(r, dict)]
                knowledge = "知识库参考:\n" + "\n".join(fragments)

            result = await self.adapter.generate(
                messages=[
                    {"role": "system", "content": (
                        "你是一名AI健康助手。基于已采集信息和知识库参考生成综合分析。"
                        "必须使用不确定表达(可能、建议、倾向于考虑)。禁止确诊,禁止给出用药剂量。"
                    )},
                    {"role": "user", "content": (
                        f"主诉: {chief}\n已采集: {collected_info}\n{knowledge}\n请给出综合分析。"
                    )},
                ],
                max_tokens=1024, temperature=0.3,
            )

            content = result.get("content", "")
            if not content:
                raise RuntimeError("LLM returned empty content")
            if not self._check_safe(content):
                raise RuntimeError(f"LLM output rejected by safety check")
            return content + f"\n\n{disclaimer}"

        except (LLMAPIError, LLMRateLimitError, LLMTimeoutError):
            raise
        except Exception as e:
            logger.error("DiagnosisAgent LLM failed: %s", e, exc_info=True)
            raise

    @staticmethod
    def _check_safe(content: str) -> bool:
        import re
        neg = r'(?<![不没未难无可应须能])'
        return not any(re.search(p, content) for p in [
            neg + r'确诊[^断排检筛查]', neg + r'保证[能可会]', r'肯定没问题',
        ])

