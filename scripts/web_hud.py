"""
Web HUD Server — 从 harness.py 拆分的独立模块
SSE 实时推送 + 轮询 fallback 的多项目可视化面板
"""
import json, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import urllib.parse

from lib.compat import FileLock
from lib.pipeline import pipeline_is_terminal as _pipeline_is_terminal

WEB_HUD_PORT = 1603


def _load_web_hud_html():
    html_path = Path(__file__).resolve().parent / "web_hud.html"
    return html_path.read_text(encoding="utf-8")


def _scan_eval_results():
    eval_dir = Path(__file__).resolve().parent.parent / "eval" / "results"
    if not eval_dir.exists():
        return []
    history = []
    for f in sorted(eval_dir.glob("eval-*.json")):
        try:
            try:
                raw = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raw = f.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw)
            summary = data.get("summary", {})
            ts = data.get("timestamp", "")
            date_str = ts[:10] if ts else f.stem.replace("eval-", "")[:8]
            if len(date_str) == 8 and "-" not in date_str:
                date_str = date_str[:4] + "-" + date_str[4:6] + "-" + date_str[6:8]
            total = summary.get("total_tests", 0)
            passed = summary.get("total_pass", 0)
            score = summary.get("weighted_score", 0)
            history.append({
                "date": date_str,
                "score": round(score, 4),
                "pass_count": passed,
                "total": total,
                "pass_rate": round(passed / total, 4) if total > 0 else 0,
            })
        except Exception:
            pass
    return history


def _inject_workers_into_state(state, proj_path):
    if not state:
        return state
    workers_dir = Path(proj_path) / ".claude" / "workers" if proj_path else None
    if not workers_dir or not workers_dir.exists():
        return state
    workers = []
    for f in sorted(workers_dir.glob("worker-*.json")):
        try:
            w = json.loads(f.read_text(encoding="utf-8"))
            workers.append(w)
        except Exception:
            pass
    if workers:
        for s in state.get("pipeline", []):
            if s["name"] == "implement":
                s["workers"] = workers
                break
    return state


def start_web_hud(port=WEB_HUD_PORT, bind="127.0.0.1",
                  prune_sessions_fn=None, load_state_fn=None, state_file=None):
    """启动 Web HUD 服务器

    Args:
        prune_sessions_fn: 清理并返回 session 索引的函数
        load_state_fn: 加载 state 的函数（无参数）
        state_file: 默认 state 文件路径
    """

    class HUDHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)

            if parsed.path == '/api/projects':
                projects = self._find_all_projects()
                self._json_response(projects)

            elif parsed.path == '/api/state':
                params = urllib.parse.parse_qs(parsed.query)
                proj_path = params.get("project", [None])[0]
                st = self._load_project_state(proj_path)
                if st:
                    st = _inject_workers_into_state(st, proj_path)
                    self._json_response(st)
                else:
                    self.send_response(404)
                    self.end_headers()

            elif parsed.path == '/api/events':
                params = urllib.parse.parse_qs(parsed.query)
                proj_path = params.get("project", [None])[0]
                self._handle_sse(proj_path)

            elif parsed.path == '/api/eval-history':
                self._json_response(_scan_eval_results())

            else:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(_load_web_hud_html().encode('utf-8'))

        def _handle_sse(self, proj_path):
            if proj_path:
                sf = Path(proj_path) / ".claude" / "harness-state.json"
            else:
                sf = state_file
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('Access-Control-Allow-Origin', f'http://localhost:{port}')
            self.end_headers()
            last_mtime = 0.0
            projects_mtime = 0.0
            # v3.4.4 MEDIUM-A fix：SSE 总时长上限 1 小时，避免客户端不主动断开
            # 时连接线程永久占用（Chrome 后台标签 / 浏览器进程残留场景）。
            # 客户端会自动重连——浏览器 EventSource 默认行为。
            SSE_MAX_DURATION_SEC = 3600
            HEARTBEAT_INTERVAL_SEC = 15  # 定期发 SSE comment 探测客户端是否还在
            start_ts = time.time()
            last_heartbeat = start_ts
            try:
                while True:
                    if time.time() - start_ts > SSE_MAX_DURATION_SEC:
                        break  # 强制断开，客户端 EventSource 会自动重连
                    try:
                        cur_mtime = sf.stat().st_mtime if sf.exists() else 0.0
                    except OSError:
                        cur_mtime = 0.0
                    if cur_mtime > last_mtime:
                        last_mtime = cur_mtime
                        st = self._load_project_state(proj_path if proj_path else None)
                        if st:
                            st = _inject_workers_into_state(st, proj_path)
                            payload = json.dumps(st, ensure_ascii=False)
                            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                            self.wfile.flush()
                    now_ts = time.time()
                    if now_ts - projects_mtime > 10:
                        projects_mtime = now_ts
                        projs = self._find_all_projects()
                        payload = json.dumps(projs, ensure_ascii=False)
                        self.wfile.write(f"event: projects\ndata: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    # SSE comment 心跳探测：客户端死了 wfile.write 会抛 BrokenPipe，主动退出
                    if now_ts - last_heartbeat > HEARTBEAT_INTERVAL_SEC:
                        last_heartbeat = now_ts
                        self.wfile.write(b":hb\n\n")
                        self.wfile.flush()
                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass

        def _is_completed(self, st):
            if not st.get("current_stage"):
                return True
            return _pipeline_is_terminal(st.get("pipeline", []))

        def _project_info(self, proj_path, st, index_entry=None):
            activity = st.get("activity", []) or []
            last_activity = activity[-1] if activity else None
            impl_stage = next((s for s in st.get("pipeline", []) if s.get("name") == "implement"), {})
            phases = impl_stage.get("phases", []) if impl_stage else []
            phase_total = len(phases)
            phase_done = sum(1 for p in phases if p.get("status") == "DONE")
            phase_current = next((p for p in phases if p.get("status") == "IN_PROGRESS"), None)
            return {
                "path": str(proj_path),
                "name": st.get("project", Path(proj_path).name),
                "task": st.get("task", {}).get("name", ""),
                "current_stage": st.get("current_stage", ""),
                "session_id": st.get("session_id", ""),
                "completed": self._is_completed(st),
                "updated_at": st.get("updated_at", ""),
                "finished_at": (index_entry or {}).get("finished_at"),
                "last_activity": last_activity,
                "phase_progress": {
                    "done": phase_done,
                    "total": phase_total,
                    "current": phase_current.get("name") if phase_current else None,
                } if phase_total else None,
            }

        def _find_all_projects(self):
            index = prune_sessions_fn()
            projects = []
            seen = set()
            for sid in sorted(index, key=lambda k: index[k].get("started_at", ""), reverse=True):
                entry = index[sid]
                proj = entry.get("project", "")
                if not proj or proj in seen:
                    continue
                sf = Path(proj) / ".claude" / "harness-state.json"
                if not sf.exists():
                    continue
                try:
                    st = json.loads(sf.read_text(encoding="utf-8"))
                    projects.append(self._project_info(proj, st, entry))
                    seen.add(proj)
                except (OSError, json.JSONDecodeError):
                    pass
            return projects

        def _load_project_state(self, proj_path):
            if proj_path:
                allowed = {p.get("path", "") for p in self._find_all_projects()}
                resolved = str(Path(proj_path).resolve())
                if resolved not in {str(Path(a).resolve()) for a in allowed}:
                    return None
                sf = Path(proj_path) / ".claude" / "harness-state.json"
            else:
                sf = state_file
            try:
                lock = FileLock(str(sf) + ".lock", timeout=2)
                with lock:
                    return json.loads(sf.read_text(encoding="utf-8"))
            except Exception:
                return None

        def _json_response(self, data):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', f'http://localhost:{port}')
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

        def log_message(self, fmt, *a):
            pass

    server = ThreadingHTTPServer((bind, port), HUDHandler)
    server.daemon_threads = True
    print(f"Dev Harness Web HUD: http://{bind}:{port}")
    print("SSE realtime + polling fallback | Ctrl+C stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("\nWeb HUD stopped")
