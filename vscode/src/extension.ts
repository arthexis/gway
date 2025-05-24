import * as vscode from 'vscode';
import { spawn } from 'child_process';
import * as path from 'path';

function runGway(args: string[]) {
  // Pick your interpreter or assume `gway` is on PATH:
  const cmd = 'gway';
  const output = vscode.window.createOutputChannel('gway');
  output.clear();
  output.show(true);

  const proc = spawn(cmd, args, {
    cwd: vscode.workspace.rootPath,
    shell: true
  });

  proc.stdout.on('data', (b) => output.append(b.toString()));
  proc.stderr.on('data', (b) => output.append(b.toString()));
  proc.on('close', (code) => {
    output.appendLine(`\nProcess exited with code ${code}`);
  });
}

export function activate(context: vscode.ExtensionContext) {
  const runFile = vscode.commands.registerCommand('gway.runFile', () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      return vscode.window.showErrorMessage('No open file.');
    }
    runGway([editor.document.fileName]);
  });

  const runSelection = vscode.commands.registerCommand('gway.runSelection', () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      return vscode.window.showErrorMessage('No open file.');
    }
    const sel = editor.selection;
    const text = editor.document.getText(sel).trim();
    if (!text) {
      return vscode.window.showWarningMessage('Nothing selected.');
    }
    // pass selection as argument; adjust your CLI to accept this flag
    runGway([editor.document.fileName, '--selection', JSON.stringify(text)]);
  });

  context.subscriptions.push(runFile, runSelection);
}

export function deactivate() {}
