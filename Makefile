.PHONY: help setup demo demo-offline test cov lint typecheck fmt check build ci precommit serve-news serve-pdf serve-price clean

PY ?= python
PKG := src

help:
	@echo "make setup         安装依赖（含 dev）"
	@echo "make demo          跑一次完整简报生成（联网，失败自动降级 fixture）"
	@echo "make demo-offline  强制离线跑一次完整简报生成"
	@echo "make test          运行测试"
	@echo "make cov           运行测试并统计覆盖率"
	@echo "make lint          静态检查（ruff check + format --check）"
	@echo "make typecheck     静态类型检查（mypy strict）"
	@echo "make fmt           自动格式化"
	@echo "make check         提交前全量自检：lint + typecheck + test + 离线自检"
	@echo "make build         构建 sdist 与 wheel，并校验 fixture 已打包"
	@echo "make ci            本地复现 CI：check + build"
	@echo "make precommit     安装 git 提交前钩子"
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

cov:
	$(PY) -m pytest --cov=mining_brief --cov-report=term-missing

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

typecheck:
	$(PY) -m mypy

fmt:
	$(PY) -m ruff check --fix . && $(PY) -m ruff format .

# 与 CI 的 lint / test 两个 job 保持一致：本地先跑通再推
check: lint typecheck test
	$(PY) -m mining_brief.cli --offline selftest

build:
	$(PY) -m build
	$(PY) scripts/check_wheel.py

ci: check build

precommit:
	$(PY) -m pre_commit install
	@echo "已安装 pre-commit 钩子；首次运行会自动下载钩子仓库"

serve-news:
	PYTHONPATH=$(PKG) $(PY) -m mining_brief.servers.news_server

serve-pdf:
	PYTHONPATH=$(PKG) $(PY) -m mining_brief.servers.pdf_server

serve-price:
	PYTHONPATH=$(PKG) $(PY) -m mining_brief.servers.price_server

clean:
	rm -rf data/cache/* data/pdfs/* out dist build
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage coverage.xml htmlcov
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find . -name "*.egg-info" -type d -prune -exec rm -rf {} +
