# Contributing to FaultZero

Thank you for your interest in contributing to FaultZero!

# FaultZero へのコントリビューション

FaultZero への貢献に興味を持っていただきありがとうございます！

## Quick Start / クイックスタート

```bash
# Clone the repository
git clone https://github.com/mattyopon/infrasim.git
cd faultzero

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run linter
ruff check src/ tests/

# Run the demo
faultzero demo
```

## Development Guidelines / 開発ガイドライン

### Code Style
- Python 3.11+
- Linter: ruff
- Type hints required for public functions
- Docstrings for public classes and functions

### Testing
- All new features must include tests
- Run `pytest tests/ -v` before submitting
- Target: maintain 89+ test coverage

### Commit Messages
- Use conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- Include version bump in feat/fix commits (e.g., `feat: FaultZero vX.Y - description`)

### Pull Requests
1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Make your changes with tests
4. Run `pytest` and `ruff check`
5. Submit a PR with a clear description

## Architecture Overview / アーキテクチャ概要

```
src/infrasim/
├── cli.py              # CLI entry point (Typer)
├── model/              # Infrastructure graph model (NetworkX)
├── simulator/          # 5 simulation engines
│   ├── engine.py       # Static simulation orchestrator
│   ├── cascade.py      # Cascade failure propagation
│   ├── scenarios.py    # 30-category scenario generator
│   ├── dynamic_engine.py  # Time-stepped simulation
│   ├── ops_engine.py   # Multi-day operational simulation
│   ├── traffic.py      # 10 traffic pattern models
│   ├── whatif_engine.py # Parameter sweep analysis
│   └── capacity_engine.py # Capacity planning
├── discovery/          # Infrastructure discovery
├── feeds/              # Security news feed integration
├── api/                # FastAPI web dashboard
└── reporter/           # Report generation (HTML, CLI)
```

## License / ライセンス

MIT License — see [LICENSE](LICENSE) for details.
