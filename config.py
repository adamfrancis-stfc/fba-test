import atexit
import json
import os
import platform
import subprocess
import threading

import questionary

_ALL_PROCS: list[subprocess.Popen] = []
_ALL_PROCS_LOCK = threading.Lock()

_LABEL_COLORS = [31, 32, 33, 34, 35, 36, 91, 92, 93, 94, 95, 96]  # red, green, yellow, blue, magenta, cyan + bright variants
_color_cache: dict[str, str] = {}
_color_lock = threading.Lock()

def _stream_output(proc, label, lock):
    for line in proc.stdout:
        safe_print(f"[{label}] {line}", end="", lock=lock)


def _kill_process_tree(proc: subprocess.Popen):
    """Popen.terminate() only kills the shell (since shell=True), not
    children like the actual node process npm spawns. Need to kill the
    whole tree explicitly, and the mechanism differs by OS."""
    if proc.poll() is not None:
        return  # already exited

    if platform.system() == "Windows":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
        )
    else:
        import os
        import signal
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass


def _cleanup_procs():
    with _ALL_PROCS_LOCK:
        procs = list(_ALL_PROCS)
    for proc in procs:
        _kill_process_tree(proc)

def _color_for_label(label: str) -> str:
    with _color_lock:
        if label not in _color_cache:
            code = _LABEL_COLORS[len(_color_cache) % len(_LABEL_COLORS)]
            _color_cache[label] = f"\x1b[{code}m"
        return _color_cache[label]

def safe_print(message: str, end: str = '\n', lock: threading.Lock | None = None):
    if lock:
        with lock:
            print(message, end=end)
    else:
        print(message, end=end)

class Step:
    def __init__(self, type: str, steps: list | None = None, label: str | None = None, cwd: str | None = None, command: str | None = None, background: bool | None = None, condition: str | None = None, hidden: bool | None = None):
        self.type = type
        self.steps = steps
        self.label = label
        self.cwd = cwd
        self.command = command
        self.background = background
        self.condition = condition
        self.hidden = hidden

    @staticmethod
    def from_dict(d: dict):
        step_type = d['type']
        if 'condition' in d.keys():
            condition = d['condition']
        else:
            condition = None
        if 'hidden' in d.keys():
            hidden = d['hidden']
        else:
            hidden = False
        if step_type == 'sequence' or step_type == 'concurrent':
            return Step(
                type=step_type,
                steps=[Step.from_dict(step) for step in d['steps']],
                condition=condition
            )
        elif step_type == 'command':
            if 'background' in d.keys():
                background = d['background']
            else:
                background = False
            return Step(
                type=step_type,
                label=d['label'],
                cwd=d['cwd'],
                command=d['command'],
                background=background,
                condition=condition,
                hidden=hidden
            )
        else:
            raise ValueError(f'Unknown step type: {step_type}')

    def run_command(self, lock: threading.Lock | None = None) -> bool:
        if self.type != 'command':
            print('Invalid command passed to run_command method')
            return False
        if not (self.cwd and self.label and self.command):
            print('Invalid command passed to run_command method')
            return False

        popen_kwargs = dict(
            shell=True,
            cwd=self.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        if platform.system() != "Windows":
            import os
            popen_kwargs["preexec_fn"] = os.setsid  # own process group, for clean killing later

        proc = subprocess.Popen(self.command, **popen_kwargs)
        with _ALL_PROCS_LOCK:
            _ALL_PROCS.append(proc)

        RESET = "\x1b[0m"
        color = _color_for_label(self.label)

        if self.background:
            if not self.hidden:
                threading.Thread(
                    target=_stream_output, args=(proc, self.label, lock), daemon=True
                ).start()
            safe_print(f"{color}[{self.label}]{RESET} started in background (pid {proc.pid})\n", lock=lock)
            return True  # don't wait — move on immediately

        for line in proc.stdout:
            if not self.hidden:
                safe_print(f"{color}[{self.label}]{RESET} {line}", end="", lock=lock)
        proc.wait()
        with _ALL_PROCS_LOCK:
            _ALL_PROCS.remove(proc)
        if proc.returncode != 0:
            safe_print(f"{color}[{self.label}]{RESET} FAILED (exit {proc.returncode})", lock=lock)
            return False
        return True


    def run_sequence(self, options: dict[str, bool], lock: threading.Lock | None = None) -> bool:
        if not self.steps:
            print('Invalid steps passed to run_sequence method')
            return False

        for step in self.steps:
            if not step.run(options, lock):
                return False

        return True

    def run_concurrent(self, options: dict[str, bool]) -> bool:
        if not self.steps:
            print('Invalid steps passed to run_concurrent method')
            return False

        lock = threading.Lock()
        threads = []
        results: list[bool] = []

        def runner(current_step: Step):
            results.append(current_step.run(options, lock))

        for step in self.steps:
            t = threading.Thread(target=runner, args=(step,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        passed = True
        for result in results:
            if not result:
                passed = False

        return passed

    def run(self, options: dict[str, bool], lock: threading.Lock | None = None) -> bool:
        if self.condition:
            if (not self.condition in options.keys()) or (options[self.condition] == False):
                return True

        if self.type == 'command':
            return self.run_command(lock)
        elif self.type == 'sequence':
            return self.run_sequence(options, lock)
        elif self.type == 'concurrent':
            return self.run_concurrent(options)
        else:
            return False

class AppConfig:
    def __init__(self, label: str, repo: str, cwd: str, options: list[dict[str, str]], test: Step):
        self.label = label
        self.repo = repo
        self.cwd = cwd
        self.options = options
        self.test = test
        self.registered_options: dict[str, bool] = {}
        self._instantiate_options()

    @staticmethod
    def from_config_file(path: str):
        with open(path, 'r') as f:
            file_config = json.load(f)

        if 'options' in file_config.keys():
            options = file_config['options']
        else:
            options = []

        return AppConfig(
            label=file_config['label'],
            repo=file_config['repo'],
            cwd=file_config['cwd'],
            options=options,
            test=Step.from_dict(file_config['test']),
        )

    def _instantiate_options(self):
        for option in self.options:
            self.registered_options[option['key']] = False

    def checkout_branch(self, branch: str):
        subprocess.run(["git", "checkout", branch], cwd=self.cwd)
        subprocess.run(["git", "pull"], cwd=self.cwd)

    def register_options(self):
        print()
        if len(self.options) > 0:
            choices = [questionary.Choice(
                title=option['label'],
                value=option,
                checked=True
            ) for option in self.options]
            selected = questionary.checkbox(
                "Configure test run",
                choices=choices
            ).ask()
            if selected:
                for opt in selected:
                    self.registered_options[opt['key']] = True
            print()

    def run_test(self) -> bool:
        result = self.test.run(self.registered_options)
        _cleanup_procs()
        return result

def load_all_apps() -> list[AppConfig]:
    configs = os.listdir('repos')
    apps: list[AppConfig] = []
    for config in configs:
        if os.path.isfile(os.path.join('repos', config)):
            apps.append(AppConfig.from_config_file(os.path.join('repos', config)))
    return apps

atexit.register(_cleanup_procs)