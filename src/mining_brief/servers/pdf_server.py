"""mineral-pdf-mcp —— 从 NI 43-101 技术报告 PDF 中抽取资源量。

工具签名（对外契约，勿随意改动）::

    extract_resources(pdf_url: str) -> ResourceTable

抽取链路
--------
1. 下载 PDF（支持 http(s):// 与本地路径 / file://），落盘到 ``data/pdfs/`` 做缓存；
2. 用 pdfplumber 逐页取文本，先做**关键词预筛**（Indicated / Inferred / Mineral Resource）
   把候选页缩到 1~4 页 —— 这步很关键，NI 43-101 动辄 200+ 页，整本丢给模型既贵又不准；
3. 把候选页文本交给强模型，用严格 JSON Schema 抽结构化结果；
4. 用 Pydantic 校验 + 单位归一（吨 → Mt），产出 ``confidence`` 与 ``warnings``；
5. 任何环节失败或未配置 LLM 时，降级读 ``fixtures/resources_*.json``，并在 warnings 中说明。

**抽取结果不是投资建议，须经合资格人士（QP）复核。**
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from mining_brief import cache, net
from mining_brief.config import FIXTURES_DIR, get_settings
from mining_brief.llm import LLM, LLMUnavailable
from mining_brief.models import ResourceRow, ResourceTable

logger = logging.getLogger(__name__)

mcp = FastMCP("mineral-pdf")

PAGE_HINTS = (
    "mineral resource",
    "resource estimate",
    "indicated",
    "inferred",
    "measured resource",
    "tonnes",
    "grade",
)
MAX_CANDIDATE_PAGES = 4
MAX_CHARS_PER_PAGE = 5000

SYSTEM_PROMPT = """你是矿业技术报告信息抽取专家。你的唯一任务是从 NI 43-101 技术报告的
页面文本中抽取**矿产资源量表格**，并输出严格 JSON。

硬性规则：
1. 只抽取文本中明确出现的数据，禁止推算、禁止补全、禁止使用你的先验知识。
2. 矿石量一律换算为 Mt（百万吨）。原文若为 tonnes，除以 1e6；若为 kt，除以 1e3。
3. grade 与 grade_unit 必须成对出现；grade_unit 只允许 "g/t" 或 "%"。
4. contained_metal 与 contained_unit 必须成对出现；contained_unit 用 "oz" / "t" / "kt" / "Moz"。
5. category 只允许 Indicated / Inferred / Measured / Proven / Probable，原样保留原文用词。
6. 若某字段在文本中找不到，填 null（字符串填 ""），**不要猜测**。
7. 若整页没有任何资源量数据，rows 返回空数组。
8. confidence 是你对本次抽取正确性的自评，0~1，宁可低报不要高报。
9. warnings 中记录所有让你不确定的点（单位歧义、表格错位、数字被截断等）。

只输出 JSON，不要任何解释文字。"""

USER_TEMPLATE = """来源：{url}
候选页码：{pages}

页面文本如下（页与页之间用 ===== PAGE n ===== 分隔）：

{content}

请输出如下结构的 JSON：
{{
  "project": "项目名称",
  "commodity": "矿种，如 gold / copper / lithium",
  "effective_date": "YYYY-MM-DD 或空字符串",
  "rows": [
    {{
      "category": "Indicated",
      "ore_mt": 12.3,
      "grade": 1.45,
      "grade_unit": "g/t",
      "contained_metal": 573000,
      "contained_unit": "oz"
    }}
  ],
  "confidence": 0.0,
  "warnings": []
}}"""


def _local_pdf_path(url: str) -> Path | None:
    """判断是否为本地 PDF 路径。"""
    if url.startswith("file://"):
        return Path(url[7:])
    candidate = Path(url)
    if candidate.exists() and candidate.suffix.lower() == ".pdf":
        return candidate
    return None


def _download_pdf(url: str) -> Path:
    """下载并缓存 PDF，返回本地路径。"""
    settings = get_settings()
    pdf_dir = settings.cache_dir.parent / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    target = pdf_dir / f"{digest}.pdf"
    if target.exists() and target.stat().st_size > 1024:
        return target

    local = _local_pdf_path(url)
    if local is not None:
        return local

    data = net.get_bytes(url, timeout=settings.http_timeout * 3)
    if not data.startswith(b"%PDF"):
        raise ValueError(f"目标不是 PDF（前 8 字节：{data[:8]!r}）")
    target.write_bytes(data)
    return target


def _page_texts(pdf_path: Path) -> list[str]:
    import pdfplumber  # 延迟导入：未安装时 server 仍可启动并给出清晰报错

    texts: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or "")
    return texts


def _candidate_pages(texts: list[str]) -> list[int]:
    """返回命中关键词的页码（1-based），按命中强度排序取前 N 页。"""
    scored: list[tuple[int, int]] = []
    for idx, text in enumerate(texts):
        low = text.lower()
        score = sum(1 for hint in PAGE_HINTS if hint in low)
        if score >= 2:
            scored.append((score, idx))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return sorted(idx + 1 for _, idx in scored[:MAX_CANDIDATE_PAGES])


def _load_fixture(commodity_hint: str = "") -> dict:
    path = FIXTURES_DIR / "resources_pilbara.json"
    if not path.exists():
        return {
            "project": "",
            "commodity": commodity_hint,
            "rows": [],
            "confidence": 0.0,
            "warnings": ["无可用 fixture，且未能从 PDF 抽取到数据"],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_rows(raw_rows: list[dict]) -> tuple[list[ResourceRow], list[str]]:
    """单位与数值归一。模型偶尔会给出 % 写进 grade_unit 之外的值，这里统一收口。"""
    rows: list[ResourceRow] = []
    warnings: list[str] = []
    for item in raw_rows:
        try:
            row = ResourceRow.model_validate(item)
        except ValidationError as exc:
            warnings.append(f"丢弃非法行 {item!r}：{exc.errors()[:1]}")
            continue
        if row.ore_mt is not None and row.ore_mt > 1e5:
            warnings.append(f"{row.category} 矿石量 {row.ore_mt} 疑似未换算单位，已除以 1e6")
            row.ore_mt = round(row.ore_mt / 1e6, 4)
        if row.grade is not None and row.grade_unit not in {"g/t", "%"}:
            warnings.append(f"{row.category} 品位单位异常：{row.grade_unit!r}")
        rows.append(row)
    return rows, warnings


def _extract_with_llm(url: str, pages: list[int], texts: list[str]) -> dict:
    llm = LLM()
    if not llm.available:
        raise LLMUnavailable("未配置 LLM_API_KEY")

    chunks = []
    for page_no in pages:
        body = texts[page_no - 1][:MAX_CHARS_PER_PAGE]
        chunks.append(f"===== PAGE {page_no} =====\n{body}")
    payload = llm.complete_json(
        SYSTEM_PROMPT,
        USER_TEMPLATE.format(url=url, pages=pages, content="\n\n".join(chunks)),
    )

    rows, warnings = _normalize_rows(payload.get("rows") or [])
    extra = list(payload.get("warnings") or [])
    confidence = float(payload.get("confidence") or 0.0)
    if not rows:
        confidence = min(confidence, 0.2)

    table = ResourceTable(
        project=str(payload.get("project") or ""),
        commodity=str(payload.get("commodity") or ""),
        effective_date=str(payload.get("effective_date") or ""),
        rows=rows,
        source_url=url,
        source_pages=pages,
        confidence=max(0.0, min(confidence, 1.0)),
        warnings=warnings + [str(w) for w in extra],
    )
    return table.model_dump()


@mcp.tool()
def extract_resources(pdf_url: str) -> dict:
    """从 NI 43-101 技术报告 PDF 中抽取 Indicated / Inferred 资源量。

    Args:
        pdf_url: PDF 的 http(s) URL、本地绝对路径，或 file:// URI。

    Returns:
        ResourceTable 字典，含 project / commodity / effective_date / rows /
        source_pages / confidence / warnings。抽取失败时 rows 为空且 warnings 说明原因。

    注意：
        * 本工具仅做**信息抽取**，结果不构成任何投资建议，须由合资格人士复核。
        * 使用前请确认对目标 PDF 的抓取与再利用符合其许可条款。
    """
    if not pdf_url or not pdf_url.strip():
        return {"error": "pdf_url 不能为空"}

    url = pdf_url.strip()
    settings = get_settings()

    # 显式请求内置示例数据：用于离线 demo，避免用假 URL 去发真实网络请求。
    if url.startswith("fixture://"):
        table = _load_fixture()
        table["source_pages"] = []
        table["warnings"] = list(table.get("warnings") or []) + [
            "本次为 fixture:// 显式请求，返回内置示例数据，非真实抽取结果"
        ]
        return table

    if settings.offline:
        table = _load_fixture()
        table.setdefault("source_url", url)
        table.setdefault("source_pages", [])
        table["warnings"] = list(table.get("warnings") or []) + ["离线模式：返回内置 fixture"]
        return table

    key = cache.make_key("pdf", url)

    def loader() -> dict:
        try:
            pdf_path = _download_pdf(url)
            texts = _page_texts(pdf_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pdf: 读取失败 %s: %s", url, exc)
            table = _load_fixture()
            table["source_url"] = url
            table["source_pages"] = []
            table["confidence"] = 0.0
            table["warnings"] = list(table.get("warnings") or []) + [f"PDF 读取失败：{exc}"]
            return table

        pages = _candidate_pages(texts)
        if not pages:
            table = _load_fixture()
            table["source_url"] = url
            table["source_pages"] = []
            table["confidence"] = 0.0
            table["warnings"] = list(table.get("warnings") or []) + [
                f"在 {len(texts)} 页中未定位到资源量表格，建议人工复核"
            ]
            return table

        try:
            return _extract_with_llm(url, pages, texts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pdf: 模型抽取失败 %s: %s", url, exc)
            table = _load_fixture()
            table["source_url"] = url
            table["source_pages"] = pages
            table["confidence"] = 0.0
            table["warnings"] = list(table.get("warnings") or []) + [f"模型抽取失败：{exc}"]
            return table

    try:
        return cache.cached(key, loader)
    except Exception as exc:  # noqa: BLE001
        table = _load_fixture()
        table["source_url"] = url
        table["warnings"] = list(table.get("warnings") or []) + [f"抽取链路异常：{exc}"]
        return table


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
