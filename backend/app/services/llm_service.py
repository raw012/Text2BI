import json
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from ..config import settings

T = TypeVar("T", bound=BaseModel)
SKILLS_ROOT = Path(__file__).resolve().parents[2] / "skills"


@lru_cache(maxsize=8)
def load_skill(skill_name: str) -> str:
    path = SKILLS_ROOT / skill_name / "SKILL.md"
    return path.read_text(encoding="utf-8")


def _extract_json(text: str) -> dict[str, Any] | None:
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None


def qwen_structured(
    skill_name: str,
    task: str,
    payload: dict[str, Any],
    output_model: type[T],
) -> T | None:
    """Ask Qwen to reason over trusted metadata, then validate its JSON contract."""
    if not settings.qwen_api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=settings.qwen_model,
            temperature=0.1,
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            timeout=30,
            max_retries=0,
        )
        response = model.invoke(
            [
                (
                    "system",
                    f"{load_skill(skill_name)}\n\n"
                    "Apply the Data Integrity Rules strictly. Reason from the supplied metadata only. "
                    "Never invent fields, values, calculations, or trends. Return one valid JSON object "
                    f"matching this JSON schema:\n{json.dumps(output_model.model_json_schema())}",
                ),
                ("human", json.dumps({"task": task, "input": payload}, default=str)),
            ]
        )
        parsed = _extract_json(str(response.content))
        return output_model.model_validate(parsed) if parsed else None
    except Exception:
        # Deterministic fallbacks keep the workflow available; validation catches unsafe output.
        return None


def qwen_vision_structured(
    skill_name: str,
    task: str,
    payload: dict[str, Any],
    screenshot_base64: str | None,
    output_model: type[T],
) -> T | None:
    """Use Qwen-VL for screenshot review while preserving a typed result."""
    if not settings.qwen_api_key or not screenshot_base64:
        return None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=settings.qwen_vl_model,
            temperature=0.1,
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            timeout=45,
            max_retries=0,
        )
        response = model.invoke(
            [
                SystemMessage(
                    content=(
                        f"{load_skill(skill_name)}\n\n"
                        "Evaluate the supplied screenshot, not an imagined dashboard. "
                        "Return visual or usability issues only; never judge or alter numeric accuracy. "
                        f"Return JSON matching:\n{json.dumps(output_model.model_json_schema())}"
                    )
                ),
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": json.dumps({"task": task, "input": payload}, default=str),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot_base64}"
                            },
                        },
                    ]
                ),
            ]
        )
        parsed = _extract_json(str(response.content))
        return output_model.model_validate(parsed) if parsed else None
    except Exception:
        return None
