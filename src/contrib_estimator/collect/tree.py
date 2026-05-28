"""Tree-sitter feature extraction. Cheap pre-LLM signals."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from tree_sitter import Parser
from tree_sitter_language_pack import get_language

# Map extension → tree-sitter language id
EXT_LANG = {
    ".py": "python",
    ".ts": "typescript", ".tsx": "tsx",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".java": "java",
}

# Node types we care about per language
COMMENT_TYPES = {"comment", "line_comment", "block_comment"}
FN_TYPES = {
    "function_definition", "function_declaration", "method_definition",
    "method_declaration", "arrow_function", "function",
}
TRY_TYPES = {"try_statement", "try_expression"}


@dataclass
class TreeFeatures:
    lang: str
    loc: int
    comment_ratio: float       # comment chars / total chars
    avg_fn_len: float          # mean fn body lines
    fn_count: int
    identifier_entropy: float  # Shannon entropy of identifier names
    try_density: float         # try blocks per 100 lines
    docstring_rate: float      # fns with leading docstring/jsdoc / fn_count


_PARSER_CACHE: dict[str, Parser] = {}


def _parser_for(path: Path):
    lang = EXT_LANG.get(path.suffix)
    if not lang:
        return None, None
    if lang in _PARSER_CACHE:
        return _PARSER_CACHE[lang], lang
    try:
        parser = Parser(get_language(lang))
    except Exception:
        return None, None
    _PARSER_CACHE[lang] = parser
    return parser, lang


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _identifier_entropy(idents: list[str]) -> float:
    """Shannon entropy of identifier name frequencies."""
    if not idents:
        return 0.0
    counts = Counter(idents)
    total = sum(counts.values())
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def _has_leading_docstring(fn_node, source: bytes, lang: str) -> bool:
    """Crude check: first child of body is a string/comment."""
    for child in fn_node.children:
        if child.type in {"block", "statement_block", "class_body"}:
            for inner in child.children:
                if inner.type in {"expression_statement", "string", "comment", "block_comment"}:
                    txt = source[inner.start_byte:inner.end_byte].decode("utf-8", errors="ignore")
                    if lang == "python" and txt.strip().startswith(('"""', "'''", '"', "'")):
                        return True
                    if lang in ("javascript", "typescript", "tsx", "java") and txt.strip().startswith("/**"):
                        return True
                    return False
            return False
    return False


def extract(path: Path) -> Optional[TreeFeatures]:
    """Parse file, return features. None if unsupported or parse fails."""
    parser, lang = _parser_for(path)
    if parser is None:
        return None
    try:
        source = path.read_bytes()
    except OSError:
        return None
    if not source:
        return None
    try:
        tree = parser.parse(source)
    except Exception:
        return None

    total_chars = len(source) or 1
    comment_chars = 0
    fn_lengths: list[int] = []
    idents: list[str] = []
    try_count = 0
    fns_with_doc = 0

    for node in _walk(tree.root_node):
        if node.type in COMMENT_TYPES:
            comment_chars += node.end_byte - node.start_byte
        elif node.type in FN_TYPES:
            fn_lengths.append(node.end_point[0] - node.start_point[0] + 1)
            if _has_leading_docstring(node, source, lang):
                fns_with_doc += 1
        elif node.type in TRY_TYPES:
            try_count += 1
        elif node.type == "identifier":
            idents.append(source[node.start_byte:node.end_byte].decode("utf-8", errors="ignore"))

    loc = source.count(b"\n") + 1
    fn_count = len(fn_lengths)
    return TreeFeatures(
        lang=lang,
        loc=loc,
        comment_ratio=round(comment_chars / total_chars, 3),
        avg_fn_len=round(sum(fn_lengths) / fn_count, 1) if fn_count else 0.0,
        fn_count=fn_count,
        identifier_entropy=round(_identifier_entropy(idents), 3),
        try_density=round(100 * try_count / max(loc, 1), 3),
        docstring_rate=round(fns_with_doc / fn_count, 3) if fn_count else 0.0,
    )


def features_dict(feat: Optional[TreeFeatures]) -> dict:
    """Safe dict for prompt injection. Empty if extract failed."""
    return asdict(feat) if feat else {}


# Fallback regex stats for unsupported files (rare given ext filter)
_PY_TRIPLE = re.compile(r'"""|\'\'\'')
