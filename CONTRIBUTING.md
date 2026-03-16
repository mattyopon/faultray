# Contributing to FaultRay

Thank you for your interest in contributing to FaultRay! This document provides guidelines and information for contributors.

## Getting Started

### Prerequisites
- Python 3.11+
- Git

### Development Setup

```bash
git clone https://github.com/mattyopon/faultray.git
cd faultray
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=faultray --cov-report=html

# Run specific test file
pytest tests/test_engine.py -v

# Lint
ruff check src/ tests/
```

## How to Contribute

### Reporting Bugs
1. Check [existing issues](https://github.com/mattyopon/faultray/issues) first
2. Use the bug report template
3. Include: Python version, OS, FaultRay version, steps to reproduce

### Suggesting Features
1. Open a [feature request](https://github.com/mattyopon/faultray/issues/new)
2. Describe the use case and expected behavior

### Pull Requests
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for new functionality
4. Ensure all tests pass (`pytest`)
5. Ensure code passes linting (`ruff check src/ tests/`)
6. Commit with clear messages
7. Open a Pull Request

### Code Style
- Follow PEP 8
- Use type hints for all function signatures
- Maximum line length: 100 characters
- Use `ruff` for linting

### Commit Messages
- Use conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- Example: `feat: add multi-region DR simulation engine`

## Project Structure

```
src/faultray/
├── cli/           # CLI commands (Typer)
├── api/           # Web dashboard (FastAPI)
├── simulator/     # 215+ simulation modules
├── integrations/  # External service integrations
├── ai/            # AI-powered analysis
├── feeds/         # Security feed processing
├── contracts/     # SLA/SLO validation
└── reporter/      # Report generation
```

## Code of Conduct

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

---

# FaultRay への貢献（日本語）

FaultRayへの貢献に興味をお持ちいただきありがとうございます！

## 開発環境のセットアップ

```bash
git clone https://github.com/mattyopon/faultray.git
cd faultray
pip install -e ".[dev]"
pytest  # テスト実行
```

## 貢献の方法

- **バグ報告**: [Issues](https://github.com/mattyopon/faultray/issues)でバグを報告
- **機能提案**: Feature Requestを作成
- **プルリクエスト**: fork → ブランチ作成 → テスト → PR

## コードスタイル
- PEP 8準拠
- 全関数に型ヒント
- 最大行長: 100文字
- `ruff`でリンティング
