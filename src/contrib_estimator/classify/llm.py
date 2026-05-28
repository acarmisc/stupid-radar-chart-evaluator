"""LiteLLM client. One retry on JSON parse fail."""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

import litellm
from pydantic import ValidationError

from ..config import Config
from ..schema import AxisScores
from .prompts import SYSTEM, render_user

log = logging.getLogger(__name__)


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON_OBJ_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _extract_json(text: str) -> str:
    """Strip reasoning, fences, surrounding prose. Return best JSON object substring."""
    t = _THINK_RE.sub("", text).strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    t = t.strip()
    if t.startswith("{") and t.endswith("}"):
        return t
    m = _JSON_OBJ_RE.search(t)
    return m.group(0) if m else t


def classify_chunk(
    cfg: Config,
    file_rel: str,
    authors: list[str],
    features: dict,
    code: str,
    repo_priors: str = "",
) -> Optional[AxisScores]:
    """Score one chunk. None if both attempts fail."""
    user = render_user(file_rel, authors, features, code, repo_priors=repo_priors)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

    for attempt in range(2):
        try:
            resp = litellm.completion(
                model=cfg.model_classify,
                messages=messages,
                api_base=cfg.litellm_base_url,
                api_key=cfg.litellm_key,
                temperature=0.0,
                max_tokens=4000,
            )
            raw = resp["choices"][0]["message"]["content"] or ""
            finish = resp["choices"][0].get("finish_reason")
            if not raw:
                log.warning("empty content on %s (finish=%s)", file_rel, finish)
            return AxisScores.model_validate(json.loads(_extract_json(raw)))
        except (json.JSONDecodeError, ValidationError) as e:
            log.warning("parse fail attempt %d on %s: %s | raw=%r", attempt, file_rel, e, raw[:200] if 'raw' in dir() else '')
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "Previous response was not valid JSON. Output ONLY the JSON object on a single line, no fences, no prose, no reasoning."})
        except Exception as e:
            log.error("llm call failed on %s: %s", file_rel, e)
            return None
    return None
