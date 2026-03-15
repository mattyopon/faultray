# FaultZero VS Code Extension

Infrastructure resilience score in your IDE. View your FaultZero resilience score directly from the VS Code status bar, run scans, and simulate failures without leaving your editor.

# FaultZero VS Code 拡張機能（日本語）

IDE上でインフラ耐障害スコアを確認できる VS Code 拡張機能です。ステータスバーから FaultZero のレジリエンススコアを直接確認し、スキャンや障害シミュレーションをエディタ内で実行できます。

## Prerequisites / 前提条件

- VS Code 1.80.0 or later
- FaultZero CLI installed (`pip install faultzero`)

## Installation / インストール

### From source / ソースから

```bash
cd vscode-extension
npm install
npm run compile
```

Then press `F5` in VS Code to launch the Extension Development Host.

### From VSIX (when published) / VSIX から（公開後）

```bash
code --install-extension faultzero-vscode-0.1.0.vsix
```

## Features / 機能

### Status Bar Score / ステータスバースコア

The extension displays your infrastructure resilience score in the VS Code status bar. The score updates automatically and uses color-coded icons:

- Green (pass): Score >= 80
- Yellow (warning): Score >= 50
- Red (error): Score < 50

### Commands / コマンド

Open the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`) and search for:

| Command | Description |
|---------|-------------|
| `FaultZero: Scan Infrastructure` | Scan your infrastructure and generate a model file |
| `FaultZero: Run Simulation` | Run chaos simulation against your infrastructure model |
| `FaultZero: Show Score` | Open a detailed resilience score report in a webview panel |

### Configuration / 設定

| Setting | Default | Description |
|---------|---------|-------------|
| `faultzero.modelPath` | `infrasim-model.json` | Path to infrastructure model file |
| `faultzero.autoScan` | `false` | Auto-scan on file save |

## Development / 開発

```bash
npm install
npm run compile   # One-time build
npm run watch     # Watch mode for development
```

## License / ライセンス

MIT
