.PHONY: help setup demo demo-offline test lint fmt serve-news serve-pdf serve-price clean

PY ?= python
PKG := src

help:
	@echo "make setup         安装依赖（含 dev）"
	@echo "make demo          跑一次完整简报生成（联网，失败自动降级 fixture）"
	@echo "make demo-offline  强制离线跑一次完整简报生成"
	@echo "make test          运行测试"
	@echo "make lint          静态检查"
	@echo "make fmt           自动格式化"
	@echo "make serve-news    单独启动 mining-news-mcp（stdio）"
	@echo "make serve-pdf     单独启动 mineral-pdf-mcp（stdio）"
	@echo "make serve-price   单独启动 lme-price-mcp（stdio）"

setup:
	$(PY) -m pip install -e ".[dev]"

demo:
	$(PY) -m mining_brief.cli brief "生成一份关于 Pilbara 锂矿的今日简报"

demo-offline:
	MINING_BRIEF_OFFLINE=true $(PY) -m mining_brief.cli brief "生成一份关于 Pilbara 锂矿的今日简报"

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .

fmt:
	$(PY) -m ruff check --fix . && $(PY) -m ruff format .

serve-news:
	PYTHONPATH=$(PKG) $(PY) -m mining_brief.servers.news_server

serve-pdf:
	PYTHONPATH=$(PKG) $(PY) -m mining_brief.servers.pdf_server

serve-price:
	PYTHONPATH=$(PKG) $(PY) -m mining_brief.servers.price_server

clean:
	rm -rf data/cache/* data/pdfs/* out .pytest_cache .ruff_cache
