import * as vscode from 'vscode';
import { exec } from 'child_process';

let statusBarItem: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext) {
    // Status bar item showing resilience score
    statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right, 100
    );
    statusBarItem.command = 'faultray.showScore';
    statusBarItem.text = '$(shield) FaultRay: --';
    statusBarItem.tooltip = 'Click to show resilience details';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('faultray.scan', runScan),
        vscode.commands.registerCommand('faultray.simulate', runSimulation),
        vscode.commands.registerCommand('faultray.showScore', showScore),
    );

    // Initial scan
    updateScore();
}

async function runScan() {
    const terminal = vscode.window.createTerminal('FaultRay');
    terminal.sendText('faultray scan --output faultray-model.json');
    terminal.show();
}

async function runSimulation() {
    const terminal = vscode.window.createTerminal('FaultRay');
    terminal.sendText('faultray simulate --json > .faultray-results.json');
    terminal.show();
}

async function showScore() {
    // Run faultray and show results in webview
    const panel = vscode.window.createWebviewPanel(
        'faultrayScore', 'FaultRay Score', vscode.ViewColumn.One, {}
    );
    panel.webview.html = '<h1>FaultRay Score</h1><p>Loading...</p>';

    exec('faultray evaluate --json', (err, stdout) => {
        if (err) {
            panel.webview.html = `<h1>Error</h1><pre>${escapeHtml(err.message)}</pre>`;
            return;
        }
        try {
            const data = JSON.parse(stdout);
            panel.webview.html = generateScoreHtml(data);
        } catch (e) {
            panel.webview.html = `<pre>${escapeHtml(stdout)}</pre>`;
        }
    });
}

function updateScore() {
    exec('faultray simulate --json 2>/dev/null', (err, stdout) => {
        if (err) {
            statusBarItem.text = '$(shield) FaultRay: N/A';
            return;
        }
        try {
            const data = JSON.parse(stdout);
            const score = data.resilience_score || 0;
            const icon = score >= 80 ? '$(pass)' : score >= 50 ? '$(warning)' : '$(error)';
            statusBarItem.text = `${icon} FaultRay: ${score}/100`;
        } catch (e) {
            statusBarItem.text = '$(shield) FaultRay: --';
        }
    });
}

function escapeHtml(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function generateScoreHtml(data: any): string {
    const score = Number(data.resilience_score) || 0;
    return `<!DOCTYPE html>
    <html>
    <head><style>
        body { font-family: sans-serif; padding: 20px; }
        .score { font-size: 3em; font-weight: bold; }
        .green { color: #3fb950; }
        .yellow { color: #d29922; }
        .red { color: #f85149; }
    </style></head>
    <body>
        <h1>FaultRay Infrastructure Report</h1>
        <div class="score ${score >= 80 ? 'green' : score >= 50 ? 'yellow' : 'red'}">
            ${score}/100
        </div>
        <p>Scenarios: ${Number(data.total_scenarios) || 'N/A'}</p>
        <p>Critical: ${Number(data.critical) || 0} | Warning: ${Number(data.warning) || 0}</p>
    </body></html>`;
}

export function deactivate() {
    statusBarItem?.dispose();
}
