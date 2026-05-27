from __future__ import annotations

import json
import queue
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk


PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.register import openai_register  # noqa: E402


DEFAULT_MAIL_CONFIG = {
    "request_timeout": 30,
    "wait_timeout": 30,
    "wait_interval": 2,
    "providers": [
        {
            "type": "tempmail_lol",
            "enable": True,
            "api_key": "",
            "domain": [],
        }
    ],
}


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd() / "output" / "openai-register-gui"


def _default_export_file() -> Path:
    return _app_dir() / "registered_accounts.json"


def _settings_file() -> Path:
    return _app_dir() / "openai_register_gui_settings.json"


class RegisterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("OpenAI Register GUI")
        self.root.geometry("1040x820")
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.stop_event = threading.Event()
        self.runner: threading.Thread | None = None
        self.success_count = 0
        self.fail_count = 0
        self.saved_settings = self._load_settings()

        openai_register.register_log_sink = self._enqueue_log
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._drain_logs)

    def _load_settings(self) -> dict:
        try:
            parsed = json.loads(_settings_file().read_text(encoding="utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _current_settings(self) -> dict:
        return {
            "total": self.total_var.get(),
            "threads": self.threads_var.get(),
            "proxy": self.proxy_var.get(),
            "export_file": self.export_var.get(),
            "quick_mail": self.quick_mail_var.get(),
            "include_default_mail": self.include_default_mail_var.get(),
            "provider_type": self.provider_type_var.get(),
            "api_base": self.api_base_var.get(),
            "admin_password": self.admin_password_var.get(),
            "api_key": self.api_key_var.get(),
            "domains": self.domain_text.get("1.0", tk.END).strip(),
            "mail_json": self.mail_text.get("1.0", tk.END).strip(),
        }

    def _save_settings(self) -> None:
        try:
            path = _settings_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._current_settings(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            self._log(f"配置保存失败: {exc}", "red")

    def _on_close(self) -> None:
        self._save_settings()
        self.root.destroy()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        settings = ttk.LabelFrame(outer, text="注册设置", padding=10)
        settings.pack(fill=tk.X)

        ttk.Label(settings, text="注册数量").grid(row=0, column=0, sticky=tk.W)
        self.total_var = tk.StringVar(value=str(self.saved_settings.get("total") or "10"))
        ttk.Entry(settings, textvariable=self.total_var, width=10).grid(row=0, column=1, padx=(8, 20), sticky=tk.W)

        ttk.Label(settings, text="线程数").grid(row=0, column=2, sticky=tk.W)
        self.threads_var = tk.StringVar(value=str(self.saved_settings.get("threads") or "3"))
        ttk.Entry(settings, textvariable=self.threads_var, width=10).grid(row=0, column=3, padx=(8, 20), sticky=tk.W)

        ttk.Label(settings, text="代理").grid(row=0, column=4, sticky=tk.W)
        self.proxy_var = tk.StringVar(value=str(self.saved_settings.get("proxy") or ""))
        ttk.Entry(settings, textvariable=self.proxy_var, width=42).grid(row=0, column=5, padx=(8, 0), sticky=tk.EW)
        settings.columnconfigure(5, weight=1)

        export_row = ttk.Frame(settings)
        export_row.grid(row=1, column=0, columnspan=6, sticky=tk.EW, pady=(10, 0))
        export_row.columnconfigure(1, weight=1)
        ttk.Label(export_row, text="成功账号导出文件").grid(row=0, column=0, sticky=tk.W)
        self.export_var = tk.StringVar(value=str(self.saved_settings.get("export_file") or _default_export_file()))
        ttk.Entry(export_row, textvariable=self.export_var).grid(row=0, column=1, padx=8, sticky=tk.EW)
        ttk.Button(export_row, text="选择", command=self._choose_export_file).grid(row=0, column=2)

        quick_box = ttk.LabelFrame(outer, text="临时邮箱快捷配置", padding=10)
        quick_box.pack(fill=tk.X, pady=(10, 0))
        quick_box.columnconfigure(3, weight=1)

        self.quick_mail_var = tk.BooleanVar(value=bool(self.saved_settings.get("quick_mail", True)))
        ttk.Checkbutton(quick_box, text="使用快捷配置生成邮箱 JSON", variable=self.quick_mail_var).grid(
            row=0, column=0, columnspan=4, sticky=tk.W
        )
        self.include_default_mail_var = tk.BooleanVar(value=bool(self.saved_settings.get("include_default_mail", True)))
        ttk.Checkbutton(quick_box, text="同时轮询软件默认临时邮箱 tempmail_lol", variable=self.include_default_mail_var).grid(
            row=0, column=2, columnspan=2, sticky=tk.W
        )

        ttk.Label(quick_box, text="类型").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        self.provider_type_var = tk.StringVar(value=str(self.saved_settings.get("provider_type") or "cloudflare_temp_email"))
        provider_box = ttk.Combobox(
            quick_box,
            textvariable=self.provider_type_var,
            values=[
                "cloudflare_temp_email",
                "tempmail_lol",
                "moemail",
                "duckmail",
                "gptmail",
                "inbucket",
                "yyds_mail",
            ],
            state="readonly",
            width=26,
        )
        provider_box.grid(row=1, column=1, padx=(8, 20), sticky=tk.W, pady=(8, 0))

        ttk.Label(quick_box, text="API Base").grid(row=1, column=2, sticky=tk.W, pady=(8, 0))
        self.api_base_var = tk.StringVar(value=str(self.saved_settings.get("api_base") or ""))
        ttk.Entry(quick_box, textvariable=self.api_base_var).grid(row=1, column=3, padx=(8, 0), sticky=tk.EW, pady=(8, 0))

        ttk.Label(quick_box, text="Admin Password").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        self.admin_password_var = tk.StringVar(value=str(self.saved_settings.get("admin_password") or ""))
        ttk.Entry(quick_box, textvariable=self.admin_password_var, show="").grid(row=2, column=1, padx=(8, 20), sticky=tk.EW, pady=(8, 0))

        ttk.Label(quick_box, text="API Key").grid(row=2, column=2, sticky=tk.W, pady=(8, 0))
        self.api_key_var = tk.StringVar(value=str(self.saved_settings.get("api_key") or ""))
        ttk.Entry(quick_box, textvariable=self.api_key_var, show="").grid(row=2, column=3, padx=(8, 0), sticky=tk.EW, pady=(8, 0))

        ttk.Label(quick_box, text="Domain（一行一个）").grid(row=3, column=0, sticky=tk.NW, pady=(8, 0))
        self.domain_text = scrolledtext.ScrolledText(quick_box, height=3, wrap=tk.WORD)
        self.domain_text.grid(row=3, column=1, columnspan=3, padx=(8, 0), sticky=tk.EW, pady=(8, 0))
        self.domain_text.insert(tk.END, str(self.saved_settings.get("domains") or ""))

        ttk.Button(quick_box, text="同步到 JSON", command=self._sync_quick_mail_to_json).grid(
            row=4, column=3, sticky=tk.E, pady=(8, 0)
        )

        mail_box = ttk.LabelFrame(outer, text="邮箱配置 JSON", padding=10)
        mail_box.pack(fill=tk.BOTH, expand=False, pady=(10, 0))
        self.mail_text = scrolledtext.ScrolledText(mail_box, height=9, wrap=tk.NONE)
        self.mail_text.pack(fill=tk.BOTH, expand=True)
        self.mail_text.insert(tk.END, str(self.saved_settings.get("mail_json") or json.dumps(DEFAULT_MAIL_CONFIG, ensure_ascii=False, indent=2)))

        actions = ttk.Frame(outer)
        actions.pack(fill=tk.X, pady=(10, 0))
        self.start_button = ttk.Button(actions, text="开始注册", command=self._start)
        self.start_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(actions, text="停止提交新任务", command=self._stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(8, 0))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(actions, textvariable=self.status_var).pack(side=tk.LEFT, padx=(16, 0))

        log_box = ttk.LabelFrame(outer, text="日志", padding=10)
        log_box.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log_text = scrolledtext.ScrolledText(log_box, height=18, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _choose_export_file(self) -> None:
        path = filedialog.asksaveasfilename(
            title="选择成功账号导出文件",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="registered_accounts.json",
        )
        if path:
            self.export_var.set(path)
            self._save_settings()

    def _domain_values(self) -> list[str]:
        raw = self.domain_text.get("1.0", tk.END)
        return [item.strip() for item in raw.replace(",", "\n").splitlines() if item.strip()]

    def _build_quick_mail_config(self) -> dict:
        provider_type = self.provider_type_var.get().strip()
        entry: dict[str, object] = {
            "type": provider_type,
            "enable": True,
        }
        domains = self._domain_values()
        if domains:
            entry["domain"] = domains

        api_base = self.api_base_var.get().strip().rstrip("/")
        admin_password = self.admin_password_var.get().strip()
        api_key = self.api_key_var.get().strip()

        if provider_type in {"cloudflare_temp_email", "moemail", "inbucket", "yyds_mail"}:
            if api_base:
                entry["api_base"] = api_base
        if provider_type == "cloudflare_temp_email" and admin_password:
            entry["admin_password"] = admin_password
        if provider_type in {"tempmail_lol", "moemail", "duckmail", "gptmail", "yyds_mail"} and api_key:
            entry["api_key"] = api_key
        if provider_type in {"duckmail", "gptmail"} and domains:
            entry.pop("domain", None)
            entry["default_domain"] = domains[0]

        if provider_type == "cloudflare_temp_email":
            if not api_base:
                raise ValueError("cloudflare_temp_email 需要填写 API Base")
            if not admin_password:
                raise ValueError("cloudflare_temp_email 需要填写 Admin Password")
            if not domains:
                raise ValueError("cloudflare_temp_email 需要至少填写一个 Domain")

        providers = [entry]
        if self.include_default_mail_var.get():
            providers.append(
                {
                    "type": "tempmail_lol",
                    "enable": True,
                    "api_key": "",
                    "domain": [],
                }
            )

        return {
            "request_timeout": 30,
            "wait_timeout": 40,
            "wait_interval": 3,
            "providers": providers,
        }

    def _sync_quick_mail_to_json(self) -> None:
        try:
            mail_config = self._build_quick_mail_config()
        except Exception as exc:
            messagebox.showerror("邮箱配置错误", str(exc))
            return
        self.mail_text.delete("1.0", tk.END)
        self.mail_text.insert(tk.END, json.dumps(mail_config, ensure_ascii=False, indent=2))
        self._save_settings()

    def _enqueue_log(self, text: str, color: str = "") -> None:
        self.log_queue.put((str(text), str(color or "")))

    def _log(self, text: str, color: str = "") -> None:
        self._enqueue_log(text, color)

    def _drain_logs(self) -> None:
        try:
            while True:
                text, color = self.log_queue.get_nowait()
                self.log_text.configure(state=tk.NORMAL)
                tag = color or "info"
                if not self.log_text.tag_names().__contains__(tag):
                    fg = {"red": "#b91c1c", "green": "#047857", "yellow": "#a16207"}.get(tag, "#444444")
                    self.log_text.tag_configure(tag, foreground=fg)
                self.log_text.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} {text}\n", tag)
                self.log_text.see(tk.END)
                self.log_text.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_logs)

    def _read_config(self) -> tuple[int, int, str, dict, Path]:
        try:
            total = max(1, int(self.total_var.get().strip()))
            threads = max(1, int(self.threads_var.get().strip()))
        except ValueError as exc:
            raise ValueError("注册数量和线程数必须是正整数") from exc
        if self.quick_mail_var.get():
            mail_config = self._build_quick_mail_config()
            self.mail_text.delete("1.0", tk.END)
            self.mail_text.insert(tk.END, json.dumps(mail_config, ensure_ascii=False, indent=2))
        else:
            try:
                mail_config = json.loads(self.mail_text.get("1.0", tk.END))
            except json.JSONDecodeError as exc:
                raise ValueError(f"邮箱配置 JSON 格式错误: {exc}") from exc
        if not isinstance(mail_config, dict):
            raise ValueError("邮箱配置必须是 JSON 对象")
        providers = mail_config.get("providers")
        if not isinstance(providers, list) or not providers:
            raise ValueError("邮箱配置需要包含 providers 列表")
        proxy = self.proxy_var.get().strip()
        mail_config = dict(mail_config)
        if proxy:
            mail_config["proxy"] = proxy
        else:
            mail_config.pop("proxy", None)
        export_file = Path(self.export_var.get().strip() or str(_default_export_file()))
        return total, threads, proxy, mail_config, export_file

    def _start(self) -> None:
        if self.runner and self.runner.is_alive():
            return
        try:
            total, threads, proxy, mail_config, export_file = self._read_config()
        except Exception as exc:
            messagebox.showerror("配置错误", str(exc))
            return

        self.stop_event.clear()
        self.success_count = 0
        self.fail_count = 0
        openai_register.config.update({"mail": mail_config, "proxy": proxy, "total": total, "threads": threads})
        self._save_settings()
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.status_var.set("运行中")
        self.runner = threading.Thread(
            target=self._run_jobs,
            args=(total, threads, proxy, export_file),
            daemon=True,
        )
        self.runner.start()

    def _stop(self) -> None:
        self.stop_event.set()
        self._log("已请求停止：不会再提交新任务，正在等待已运行任务结束", "yellow")

    def _run_one(self, index: int, proxy: str) -> dict:
        registrar = openai_register.PlatformRegistrar(proxy)
        try:
            openai_register.step(index, "任务启动")
            return registrar.register(index)
        finally:
            registrar.close()

    def _run_jobs(self, total: int, threads: int, proxy: str, export_file: Path) -> None:
        started = time.time()
        submitted = 0
        futures = set()
        try:
            export_file.parent.mkdir(parents=True, exist_ok=True)
            self._log(f"开始注册：数量={total}，线程={threads}，成功账号导出={export_file}", "yellow")
            with ThreadPoolExecutor(max_workers=threads) as executor:
                while submitted < total and len(futures) < threads and not self.stop_event.is_set():
                    submitted += 1
                    futures.add(executor.submit(self._run_one, submitted, proxy))
                while futures:
                    finished, futures = wait(futures, return_when=FIRST_COMPLETED)
                    for future in finished:
                        try:
                            result = future.result()
                            self.success_count += 1
                            self._append_account(export_file, result)
                            self._log(f"{result.get('email')} 注册成功，已写入导出文件", "green")
                        except Exception as exc:
                            self.fail_count += 1
                            hint = openai_register._describe_register_error(exc)
                            suffix = f"；{hint}" if hint else ""
                            self._log(f"注册失败，原因: {exc}{suffix}", "red")
                    while submitted < total and len(futures) < threads and not self.stop_event.is_set():
                        submitted += 1
                        futures.add(executor.submit(self._run_one, submitted, proxy))
        except Exception as exc:
            self._log(f"任务异常结束: {exc}", "red")
        finally:
            elapsed = time.time() - started
            self._log(f"任务结束：成功 {self.success_count}，失败 {self.fail_count}，耗时 {elapsed:.1f}s", "yellow")
            self.root.after(0, self._finish_ui)

    def _append_account(self, export_file: Path, account: dict) -> None:
        item = dict(account)
        item.setdefault("exported_at", datetime.now(timezone.utc).isoformat())
        data: list[dict] = []
        if export_file.exists():
            try:
                parsed = json.loads(export_file.read_text(encoding="utf-8"))
                if isinstance(parsed, list):
                    data = [entry for entry in parsed if isinstance(entry, dict)]
            except Exception:
                data = []
        data.append(item)
        export_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._write_access_tokens(export_file, data)

    def _write_access_tokens(self, export_file: Path, accounts: list[dict]) -> None:
        tokens: list[str] = []
        seen: set[str] = set()
        for account in accounts:
            token = str(account.get("access_token") or account.get("accessToken") or "").strip()
            if token and token not in seen:
                seen.add(token)
                tokens.append(token)
        token_file = export_file.parent / "access_tokens.txt"
        token_file.write_text("\n".join(tokens) + ("\n" if tokens else ""), encoding="utf-8")

    def _finish_ui(self) -> None:
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.status_var.set(f"完成：成功 {self.success_count}，失败 {self.fail_count}")


def main() -> None:
    root = tk.Tk()
    RegisterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
