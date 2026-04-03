#!/usr/bin/env node
/**
 * Dev Harness Statusline — 嵌入 Claude Code 终端底部的一行实时状态
 *
 * 注册方式（在 settings.json 中，与已有 statusline 合并）:
 * { "statusLine": { "type": "command", "command": "node ~/.claude/plugins/dev-harness/hooks/statusline.js" } }
 *
 * stdin: Claude Code 传入的 JSON（model, contextWindow, cost 等）
 * stdout: 一行文本，显示在终端底部
 */

const fs = require('fs');
const path = require('path');

let input = '';
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
    try {
        const ccData = JSON.parse(input || '{}');
        const output = buildStatusLine(ccData);
        console.log(output);
    } catch (e) {
        console.log('DH: error');
    }
});

function buildStatusLine(ccData) {
    // ==================== Claude Code 基础信息 ====================
    const model = ccData.model?.name?.replace('claude-', '')?.substring(0, 12) || '?';
    const ctx = ccData.contextWindow;
    const ctxPct = ctx ? Math.round((ctx.used / ctx.total) * 100) : 0;
    const cost = ccData.cost?.total ? `$${ccData.cost.total.toFixed(2)}` : '';

    // ==================== Harness 状态 ====================
    const stateFile = path.join(process.cwd(), '.claude', 'harness-state.json');
    let harnessStr = '';

    try {
        const state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
        if (state && state.current_stage) {
            const task = state.task?.name || '';
            const stage = state.current_stage;
            const pipeline = state.pipeline || [];
            const done = pipeline.filter(s => s.status === 'DONE').length;
            const total = pipeline.filter(s => s.status !== 'SKIP').length;
            const errors = state.metrics?.total_errors || 0;
            const autoC = state.metrics?.auto_continues || 0;

            // implement 阶段显示 Phase 进度
            let phaseStr = '';
            const impl = pipeline.find(s => s.name === 'implement');
            if (stage === 'implement' && impl?.phases) {
                const pDone = impl.phases.filter(p => p.status === 'DONE').length;
                const pTotal = impl.phases.length;
                phaseStr = ` P${pDone}/${pTotal}`;
            }

            // 截断任务名（最多 12 字符）
            const shortTask = task.length > 12 ? task.substring(0, 11) + '…' : task;

            harnessStr = ` | DH: ${shortTask} [${stage}${phaseStr}] ${done}/${total} E:${errors} AC:${autoC}`;
        }
    } catch (e) {
        // 没有 harness 状态，不显示
    }

    return `${model} ctx:${ctxPct}% ${cost}${harnessStr}`;
}
