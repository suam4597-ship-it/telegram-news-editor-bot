from __future__ import annotations

from app.config import load_style_guide
from app.llm.client import OpenAIResponsesClient
from app.llm.prompt_loader import load_prompt
from app.llm.schemas import VALIDATION_SCHEMA, FactExtraction, ValidationIssue, ValidationOutput
from app.parsers.text_cleaner import find_ai_phrases, find_forbidden_phrases


class SummaryValidator:
    def __init__(self, client: OpenAIResponsesClient | None = None):
        self.client = client or OpenAIResponsesClient()

    async def validate(self, *, facts: FactExtraction, telegram_text: str) -> ValidationOutput:
        if not self.client.available:
            return self._fallback(facts=facts, telegram_text=telegram_text)
        prompt = load_prompt("validator_v1.md").format(
            fact_json=facts.model_dump_json(ensure_ascii=False),
            telegram_text=telegram_text,
        )
        payload = await self.client.structured_json(
            schema_name="validation_output",
            schema=VALIDATION_SCHEMA,
            prompt=prompt,
            instructions="You validate Korean Telegram financial news copy for factuality, compliance, and style.",
        )
        validation = ValidationOutput.model_validate(payload)
        local_issues = self._local_issues(telegram_text)
        if not local_issues:
            return validation
        issues = [*validation.issues, *local_issues]
        pass_value = validation.pass_ and not any(issue.severity == "high" for issue in local_issues)
        return validation.model_copy(update={"pass_": pass_value, "issues": issues})

    def _fallback(self, *, facts: FactExtraction, telegram_text: str) -> ValidationOutput:
        issues = self._local_issues(telegram_text)
        pass_value = not any(issue.severity == "high" for issue in issues)
        return ValidationOutput(
            **{
                "pass": pass_value,
                "issues": issues,
                "revised_text": telegram_text,
                "factuality_score": 0.8 if pass_value else 0.55,
                "copy_similarity_score": 0.15,
            }
        )

    def _local_issues(self, telegram_text: str) -> list[ValidationIssue]:
        guide = load_style_guide()
        issues: list[ValidationIssue] = []
        for phrase in find_forbidden_phrases(telegram_text):
            issues.append(ValidationIssue(issue_type="investment_advice", severity="high", message=f"금지 표현 포함: {phrase}"))
        for phrase in find_ai_phrases(telegram_text):
            issues.append(ValidationIssue(issue_type="style", severity="medium", message=f"기계적인 표현 포함: {phrase}"))
        if "출처:" not in telegram_text:
            issues.append(ValidationIssue(issue_type="source", severity="high", message="출처 링크가 없습니다."))
        if guide.disclaimer not in telegram_text:
            issues.append(ValidationIssue(issue_type="disclaimer", severity="medium", message="투자 권유 아님 고지가 없습니다."))
        return issues
