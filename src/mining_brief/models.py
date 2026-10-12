"""领域数据模型。所有跨模块流转的数据都走这些 Pydantic 模型，禁止裸 dict 满天飞。"""

from __future__ import annotations

from datetime import date as _date
from typing import Literal

from pydantic import BaseModel, Field

ResourceCategory = Literal["Measured", "Indicated", "Inferred", "Proven", "Probable", "Total"]
Commodity = Literal["lithium", "copper", "zinc", "iron_ore", "gold", "nickel", "cobalt"]


class Article(BaseModel):
    """一条新闻检索结果。"""

    title: str
    url: str
    source: str = Field(description="站点/媒体名，用于引用标注")
    published: str = Field(default="", description="ISO8601 日期，未知则留空")
    summary: str = Field(default="", description="原文摘要或 RSS description")


class ArticleDetail(Article):
    """文章正文（截断后）。"""

    text: str = Field(default="", description="正文纯文本，已按 max_chars 截断")
    truncated: bool = False


class ResourceRow(BaseModel):
    """NI 43-101 资源量表格的一行。"""

    category: ResourceCategory
    ore_mt: float | None = Field(default=None, description="矿石量，单位 Mt（百万吨）")
    grade: float | None = Field(default=None, description="品位数值")
    grade_unit: str = Field(default="", description="品位单位，如 g/t、%")
    contained_metal: float | None = Field(default=None, description="金属量数值")
    contained_unit: str = Field(default="", description="金属量单位，如 oz、t、kt")


class ResourceTable(BaseModel):
    """一份 PDF 中抽出的资源量汇总。"""

    project: str = ""
    commodity: str = ""
    effective_date: str = Field(default="", description="资源量估算生效日期")
    rows: list[ResourceRow] = Field(default_factory=list)
    source_url: str = ""
    source_pages: list[int] = Field(default_factory=list, description="命中的 PDF 页码，1-based")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="抽取置信度")
    warnings: list[str] = Field(default_factory=list)

    @property
    def total_ore_mt(self) -> float:
        return sum(r.ore_mt or 0.0 for r in self.rows)


class PriceQuote(BaseModel):
    """单日报价。"""

    commodity: Commodity
    date: str = Field(description="ISO8601 日期")
    price: float
    unit: str = Field(description="计价单位，如 USD/t")
    currency: str = "USD"
    source: str = ""
    source_url: str = Field(default="", description="可回溯的来源页 URL，用于简报引用")
    is_proxy: bool = Field(default=False, description="是否为代理指标（无免费直连数据源时）")
    note: str = ""


class TrendPoint(BaseModel):
    date: str
    price: float


class TrendSeries(BaseModel):
    commodity: Commodity
    days: int
    points: list[TrendPoint] = Field(default_factory=list)
    unit: str = ""
    source: str = ""
    source_url: str = ""
    is_proxy: bool = False
    change_pct: float | None = Field(default=None, description="区间涨跌幅，百分比")
    note: str = ""


class Citation(BaseModel):
    """简报中每一条结论都必须挂来源。"""

    label: str = Field(description="人类可读的来源名，如 mining.com")
    url: str
    kind: Literal["news", "pdf", "price"] = "news"


class Brief(BaseModel):
    """最终交付物。"""

    title: str
    subject: str = Field(description="简报对象，如 Pilbara 锂矿")
    generated_at: str
    news_section: str = ""
    resource_section: str = ""
    price_section: str = ""
    risk_section: str = ""
    citations: list[Citation] = Field(default_factory=list)
    degraded: list[str] = Field(default_factory=list, description="降级/缺失的数据源说明")


def today_iso() -> str:
    return _date.today().isoformat()
