import * as vscode from 'vscode';
import { exec } from 'child_process';

let statusBarItem: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext) {
    // Status bar item showing resilience score
    statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right, 100
    );
    statusBarItem.command = 'faultzero.showScore';
    statusBarItem.text = '$(shield) FaultZero: --';
    statusBarItem.tooltip = 'Click to show resilience details';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('faultzero.scan', runScan),
        vscode.commands.registerCommand('faultzero.simulate', runSimulation),
        vscode.commands.registerCommand('faultzero.showScore', showScore),
    );

    // Initial scan
    updateScore();
}

async function runScan() {
    const terminal = vscode.window.createTerminal('FaultZero');
    terminal.sendText('chaosproof scan --output faultray-model.json');
    terminal.show();
}

async function runSimulation() {
    const terminal = vscode.window.createTerminal('FaultZero');
    terminal.sendText('chaosproof simulate --json > .chaosproof-results.json');
    terminal.show();
}

async function showScore() {
    // Run chaosproof and show results in webview
    const panel = vscode.window.createWebviewPanel(
        'faultzeroScore', 'FaultZero Score', vscode.ViewColumn.One, {}
    );
    panel.webview.html = '<h1>FaultZero Score</h1><p>Loading...</p>';

    exec('chaosproof evaluate --json', (err, stdout) => {
        if (err) {
            panel.webview.html = `<h1>Error</h1><pre>${err.message}</pre>`;
            return;
        }
        try {
            const data = JSON.parse(stdout);
            panel.webview.html = generateScoreHtml(data);
        } catch (e) {
            panel.webview.html = `<pre>${stdout}</pre>`;
        }
    });
}

function updateScore() {
    exec('chaosproof simulate --json 2>/dev/null', (err, stdout) => {
        if (err) {
            statusBarItem.text = '$(shield) FaultZero: N/A';
            return;
        }
        try {
            const data = JSON.parse(stdout);
            const score = data.resilience_score || 0;
            const icon = score >= 80 ? '$(pass)' : score >= 50 ? '$(warning)' : '$(error)';
            statusBarItem.text = `${icon} FaultZero: ${score}/100`;
        } catch (e) {
            statusBarItem.text = '$(shield) FaultZero: --';
        }
    });
}

function generateScoreHtml(data: any): string {
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
        <h1>FaultZero Infrastructure Report</h1>
        <div class="score ${data.resilience_score >= 80 ? 'green' : data.resilience_score >= 50 ? 'yellow' : 'red'}">
            ${data.resilience_score}/100
        </div>
        <p>Scenarios: ${data.total_scenarios || 'N/A'}</p>
        <p>Critical: ${data.critical || 0} | Warning: ${data.warning || 0}</p>
    </body></html>`;
}

export function deactivate() {
    statusBarItem?.dispose();
}
