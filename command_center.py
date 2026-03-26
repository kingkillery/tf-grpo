from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st
import yaml

from training_free_grpo.utils import load_jsonl

ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
DISPLAY_TIME = "%Y-%m-%d %H:%M:%S"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(read_text(path)) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return payload


def relative_posix(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def format_ts(path: Path | None) -> str:
    if not path or not path.exists():
        return "n/a"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime(DISPLAY_TIME)


def config_paths(kind: str) -> list[Path]:
    if kind == "practice":
        base = ROOT / "configs" / "practice"
    elif kind == "eval":
        base = ROOT / "configs" / "eval"
    elif kind == "agent":
        base = ROOT / "configs" / "agents" / "practice"
    else:
        raise ValueError(f"Unknown config kind: {kind}")
    return sorted(base.rglob("*.yaml"))


def collect_env_requirements(agent_payload: dict[str, Any], eval_payload: dict[str, Any] | None = None) -> list[str]:
    keys: set[str] = set()

    provider = agent_payload.get("model_provider") or {}
    if isinstance(provider, dict) and provider.get("api_key_env"):
        keys.add(str(provider["api_key_env"]))

    if isinstance(eval_payload, dict):
        judge_provider = ((eval_payload.get("judge_model") or {}).get("model_provider") or {})
        if isinstance(judge_provider, dict) and judge_provider.get("api_key_env"):
            keys.add(str(judge_provider["api_key_env"]))

    for tool in agent_payload.get("tools", []):
        if not isinstance(tool, dict) or not tool.get("enabled", True):
            continue
        if tool.get("name") == "google_search":
            keys.add("SERPAPI_API_KEY")
    return sorted(keys)


def readiness_rows(keys: list[str]) -> list[dict[str, str]]:
    rows = []
    for key in keys:
        value = os.getenv(key)
        rows.append(
            {
                "name": key,
                "status": "present" if value else "missing",
                "value": "configured" if value else "not set",
            }
        )
    return rows


def dataset_preview(path_str: str, limit: int = 5) -> tuple[str, list[dict[str, Any]]]:
    path = Path(path_str)
    if not path.is_absolute():
        path = ROOT / path
    rows = load_jsonl(path)
    return relative_posix(path), rows[:limit]


def summarize_run(run_dir: Path) -> dict[str, Any]:
    stats_path = run_dir / "stats.json"
    result_path = run_dir / "result.json"
    eval_metrics_path = run_dir / "eval_metrics.json"
    experiences_path = run_dir / "experiences_final.json"
    step_dirs = sorted([p for p in run_dir.iterdir() if p.is_dir() and p.name.startswith("step_")])

    stats = read_json(stats_path) if stats_path.exists() else {}
    result = read_json(result_path) if result_path.exists() else {}
    eval_metrics = read_json(eval_metrics_path) if eval_metrics_path.exists() else {}
    experiences = read_json(experiences_path) if experiences_path.exists() else {}

    latest_step = None
    latest_step_metrics: dict[str, Any] = {}
    if stats:
        latest_step = sorted(stats.keys(), key=lambda name: int(name.split("_")[-1]))[-1]
        latest_step_metrics = stats[latest_step]

    return {
        "name": run_dir.name,
        "path": run_dir,
        "updated": format_ts(run_dir),
        "step_count": len(step_dirs),
        "has_practice": stats_path.exists(),
        "has_eval": eval_metrics_path.exists(),
        "latest_step": latest_step,
        "latest_step_metrics": latest_step_metrics,
        "eval_metrics": eval_metrics,
        "experience_count": len(experiences) if isinstance(experiences, dict) else 0,
        "result": result,
        "step_dirs": step_dirs,
    }


def discovered_runs() -> list[dict[str, Any]]:
    if not RUNS_DIR.exists():
        return []
    return sorted(
        [summarize_run(path) for path in RUNS_DIR.iterdir() if path.is_dir()],
        key=lambda item: item["path"].stat().st_mtime,
        reverse=True,
    )


def launch_command(mode: str, config_name: str) -> dict[str, Any]:
    script = "run_training_free_GRPO.py" if mode == "practice" else "run_eval.py"
    command = [
        sys.executable,
        str(ROOT / "scripts" / script),
        "--config_name",
        config_name,
        "--root",
        str(ROOT),
    ]
    proc = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return {
        "mode": mode,
        "config_name": config_name,
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "ran_at": datetime.now().strftime(DISPLAY_TIME),
    }


def metric_card(label: str, value: str, tone: str = "default") -> None:
    st.markdown(
        f"""
        <div class="metric-card tone-{tone}">
          <div class="metric-label">{label}</div>
          <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(eyebrow: str, title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="section-shell">
          <div class="eyebrow">{eyebrow}</div>
          <h2>{title}</h2>
          <p>{body}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Fraunces:opsz,wght@9..144,500;9..144,700&display=swap');

        :root {
          --bg: #f3efe6;
          --panel: rgba(255,255,255,0.68);
          --panel-strong: rgba(255,255,255,0.9);
          --ink: #161412;
          --muted: #6a6257;
          --line: rgba(22,20,18,0.12);
          --accent: #ca5f36;
          --accent-soft: rgba(202,95,54,0.12);
          --forest: #27594f;
          --forest-soft: rgba(39,89,79,0.12);
          --gold: #a98431;
          --shadow: 0 24px 80px rgba(50, 35, 19, 0.10);
        }

        .stApp {
          background:
            radial-gradient(circle at top left, rgba(202,95,54,0.14), transparent 32%),
            radial-gradient(circle at top right, rgba(39,89,79,0.14), transparent 28%),
            linear-gradient(180deg, #efe7da 0%, var(--bg) 52%, #efe9df 100%);
          color: var(--ink);
        }

        .main .block-container {
          padding-top: 2.2rem;
          padding-bottom: 3rem;
          max-width: 1400px;
        }

        h1, h2, h3 {
          font-family: 'Fraunces', serif;
          letter-spacing: -0.03em;
          color: var(--ink);
        }

        p, li, div, span, label {
          font-family: 'IBM Plex Mono', monospace;
        }

        [data-testid="stSidebar"] {
          background: rgba(247, 241, 232, 0.92);
          border-right: 1px solid var(--line);
        }

        .hero-shell {
          padding: 1.6rem 1.8rem 1.3rem 1.8rem;
          background: linear-gradient(145deg, rgba(255,255,255,0.78), rgba(255,248,241,0.92));
          border: 1px solid rgba(22,20,18,0.08);
          box-shadow: var(--shadow);
          border-radius: 28px;
          position: relative;
          overflow: hidden;
          margin-bottom: 1rem;
        }

        .hero-shell:before {
          content: "";
          position: absolute;
          inset: auto -8% -45% auto;
          width: 320px;
          height: 320px;
          background: radial-gradient(circle, rgba(202,95,54,0.18), transparent 65%);
          pointer-events: none;
        }

        .hero-kicker {
          display: inline-block;
          color: var(--accent);
          font-size: 0.8rem;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          margin-bottom: 0.8rem;
        }

        .hero-title {
          font-size: clamp(2.4rem, 5vw, 4.6rem);
          line-height: 0.94;
          max-width: 9.5em;
          margin: 0;
        }

        .hero-copy {
          margin-top: 1rem;
          max-width: 70ch;
          color: var(--muted);
          line-height: 1.7;
        }

        .metric-card {
          padding: 1rem 1rem 0.9rem;
          border-radius: 22px;
          border: 1px solid var(--line);
          background: var(--panel);
          backdrop-filter: blur(10px);
          min-height: 120px;
        }

        .metric-card.tone-accent { background: linear-gradient(180deg, rgba(202,95,54,0.14), rgba(255,255,255,0.78)); }
        .metric-card.tone-forest { background: linear-gradient(180deg, rgba(39,89,79,0.14), rgba(255,255,255,0.78)); }
        .metric-card.tone-gold { background: linear-gradient(180deg, rgba(169,132,49,0.14), rgba(255,255,255,0.78)); }

        .metric-label {
          font-size: 0.72rem;
          text-transform: uppercase;
          letter-spacing: 0.16em;
          color: var(--muted);
        }

        .metric-value {
          font-family: 'Fraunces', serif;
          font-size: 2rem;
          line-height: 1.1;
          margin-top: 0.7rem;
        }

        .section-shell {
          margin: 0.6rem 0 0.75rem;
        }

        .section-shell .eyebrow {
          color: var(--accent);
          text-transform: uppercase;
          letter-spacing: 0.14em;
          font-size: 0.72rem;
          margin-bottom: 0.35rem;
        }

        .section-shell p {
          color: var(--muted);
          max-width: 78ch;
          line-height: 1.7;
        }

        .signal-strip {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 0.8rem;
          margin: 1rem 0 1.25rem;
        }

        .signal-panel {
          padding: 1rem 1.1rem;
          background: var(--panel-strong);
          border: 1px solid var(--line);
          border-radius: 20px;
        }

        .signal-panel h4 {
          font-size: 0.9rem;
          margin: 0 0 0.5rem;
          color: var(--ink);
        }

        .signal-panel p {
          color: var(--muted);
          margin: 0;
          line-height: 1.6;
          font-size: 0.84rem;
        }

        .run-card {
          padding: 1rem 1rem 0.9rem;
          border-radius: 18px;
          border: 1px solid var(--line);
          background: var(--panel);
          margin-bottom: 0.6rem;
        }

        .run-card h4 {
          margin: 0 0 0.35rem;
        }

        .run-meta {
          color: var(--muted);
          font-size: 0.8rem;
          line-height: 1.6;
        }

        .command-preview {
          padding: 1rem 1.1rem;
          border-radius: 18px;
          border: 1px solid var(--line);
          background: #191714;
          color: #efe7da;
          font-family: 'IBM Plex Mono', monospace;
          white-space: pre-wrap;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def app_header(runs: list[dict[str, Any]]) -> None:
    total_steps = sum(run["step_count"] for run in runs)
    practice_runs = sum(1 for run in runs if run["has_practice"])
    eval_runs = sum(1 for run in runs if run["has_eval"])
    st.markdown(
        """
        <section class="hero-shell">
          <div class="hero-kicker">Training-Free GRPO / Operator Surface</div>
          <h1 class="hero-title">Command Center for practice loops, eval sweeps, and experience memory.</h1>
          <p class="hero-copy">
            This control room sits on top of the existing repo workflow. Use it to inspect configs,
            validate environment readiness, launch the native scripts, and review run artifacts from
            grouped rollouts all the way through exported agent configs.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Practice Configs", str(len(config_paths("practice"))), "accent")
    with c2:
        metric_card("Eval Configs", str(len(config_paths("eval"))), "forest")
    with c3:
        metric_card("Tracked Runs", str(len(runs)), "gold")
    with c4:
        metric_card("Recorded Steps", str(total_steps or 0), "default")

    st.markdown(
        f"""
        <div class="signal-strip">
          <div class="signal-panel">
            <h4>Practice Engine</h4>
            <p>{practice_runs} run folders include batch-wise practice stats, critique artifacts, and evolving experience pools.</p>
          </div>
          <div class="signal-panel">
            <h4>Eval Surface</h4>
            <p>{eval_runs} run folders include eval rollouts and persisted metrics for Pass@k, reward, and tool-call averages.</p>
          </div>
          <div class="signal-panel">
            <h4>Artifact Chain</h4>
            <p>Browse resolved configs, shuffled epochs, step directories, exported agents, and final experience memories from one place.</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_controls() -> tuple[str, str]:
    st.sidebar.title("Control Rail")
    mode = st.sidebar.radio("Launch Mode", ["practice", "eval"], horizontal=True)
    config_kind = "practice" if mode == "practice" else "eval"
    options = config_paths(config_kind)
    selected = st.sidebar.selectbox(
        "Config",
        options,
        format_func=relative_posix,
    )
    st.sidebar.caption(f"Workspace: `{ROOT}`")
    return mode, relative_posix(selected)


def launchpad(mode: str, config_name: str) -> None:
    section_header(
        "Launchpad",
        "Run the repo-native workflows",
        "This panel executes the existing `scripts/run_training_free_GRPO.py` and `scripts/run_eval.py` entry points. Nothing here bypasses the package logic.",
    )

    config_path = ROOT / config_name
    selected_payload = read_yaml(config_path)
    agent_config_name = selected_payload["agent_config"]
    agent_payload = read_yaml(ROOT / agent_config_name)
    eval_payload = None
    if mode == "practice" and selected_payload.get("evaluation_config"):
        eval_payload = read_yaml(ROOT / selected_payload["evaluation_config"])
    elif mode == "eval":
        eval_payload = selected_payload

    needed_keys = collect_env_requirements(agent_payload, eval_payload)
    readiness = readiness_rows(needed_keys)
    missing = [row["name"] for row in readiness if row["status"] == "missing"]

    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        st.subheader("Resolved Command")
        script = "run_training_free_GRPO.py" if mode == "practice" else "run_eval.py"
        st.markdown(
            f"""
            <div class="command-preview">{sys.executable} scripts/{script} --config_name {config_name} --root {ROOT}</div>
            """,
            unsafe_allow_html=True,
        )
        st.subheader("Config Snapshot")
        st.code(yaml.safe_dump(selected_payload, sort_keys=False, allow_unicode=True), language="yaml")

    with right:
        st.subheader("Environment Readiness")
        if readiness:
            st.dataframe(readiness, use_container_width=True, hide_index=True)
        else:
            st.info("No external environment variables were inferred from this config.")

        if missing:
            st.warning("Launch is blocked until the missing environment variables are set.")
        else:
            st.success("Required environment variables are present.")

        if st.button(f"Launch {mode}", type="primary", disabled=bool(missing), use_container_width=True):
            with st.spinner(f"Running {mode}..."):
                st.session_state["last_launch"] = launch_command(mode, config_name)
            st.rerun()

    result = st.session_state.get("last_launch")
    if result:
        st.subheader("Last Launch Result")
        a, b, c = st.columns(3)
        with a:
            metric_card("Mode", str(result["mode"]).upper(), "accent")
        with b:
            metric_card("Exit Code", str(result["returncode"]), "forest" if result["returncode"] == 0 else "accent")
        with c:
            metric_card("Ran At", result["ran_at"], "gold")
        out_tab, err_tab = st.tabs(["stdout", "stderr"])
        with out_tab:
            st.code(result["stdout"] or "(no stdout)", language="text")
        with err_tab:
            st.code(result["stderr"] or "(no stderr)", language="text")


def mission_control(runs: list[dict[str, Any]]) -> None:
    section_header(
        "Mission Control",
        "See the whole system at a glance",
        "The repo has two operating modes: practice loops that build external experience memory, and eval sweeps that measure the frozen policy with or without those experiences.",
    )

    practice_configs = [read_yaml(path) for path in config_paths("practice")]
    eval_configs = [read_yaml(path) for path in config_paths("eval")]
    practice_exp_ids = [cfg.get("exp_id", "unknown") for cfg in practice_configs]
    eval_exp_ids = [cfg.get("exp_id", "unknown") for cfg in eval_configs]

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.subheader("Practice Programs")
        for cfg in practice_configs:
            st.markdown(
                f"""
                <div class="run-card">
                  <h4>{cfg.get("exp_id", "unknown")}</h4>
                  <div class="run-meta">
                    agent: {cfg.get("agent_config")}<br/>
                    eval hook: {cfg.get("evaluation_config") or "none"}<br/>
                    epochs: {(cfg.get("practice") or {}).get("epochs", "n/a")} /
                    grpo_n: {(cfg.get("practice") or {}).get("grpo_n", "n/a")} /
                    reward: {(cfg.get("practice") or {}).get("reward", "n/a")}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    with c2:
        st.subheader("Evaluation Programs")
        for cfg in eval_configs:
            st.markdown(
                f"""
                <div class="run-card">
                  <h4>{cfg.get("exp_id", "unknown")}</h4>
                  <div class="run-meta">
                    agent: {cfg.get("agent_config")}<br/>
                    dataset: {cfg.get("dataset_path")}<br/>
                    pass_k: {cfg.get("pass_k", "n/a")} /
                    verify_type: {cfg.get("verify_type", "n/a")}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.caption(
        "Configured practice experiments: "
        + ", ".join(practice_exp_ids)
        + " | Configured eval experiments: "
        + ", ".join(eval_exp_ids)
    )


def run_inspector(runs: list[dict[str, Any]]) -> None:
    section_header(
        "Runs",
        "Browse generated artifacts and telemetry",
        "Run folders are treated as first-class data products. Inspect recent metrics, step-by-step outputs, final experience memories, and exported agent configs.",
    )

    if not runs:
        st.info("No run directories found yet. Launch a practice or eval job from the Launchpad.")
        return

    selected_name = st.selectbox("Run Folder", [run["name"] for run in runs], index=0)
    run = next(item for item in runs if item["name"] == selected_name)
    run_dir = run["path"]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Updated", run["updated"], "gold")
    with c2:
        metric_card("Steps", str(run["step_count"]), "accent")
    with c3:
        metric_card("Experiences", str(run["experience_count"]), "forest")
    with c4:
        latest_pass = run["latest_step_metrics"].get("pass_at_k") if run["latest_step_metrics"] else run["eval_metrics"].get("Pass@1") or run["eval_metrics"].get("Pass@4")
        metric_card("Latest Pass", f"{latest_pass:.2f}" if isinstance(latest_pass, (int, float)) else "n/a", "default")

    stats_path = run_dir / "stats.json"
    if stats_path.exists():
        stats = read_json(stats_path)
        ordered_steps = [stats[key] for key in sorted(stats.keys(), key=lambda name: int(name.split("_")[-1]))]
        st.subheader("Practice Telemetry")
        st.line_chart(
            {
                "avg_reward": [step.get("avg_reward", 0.0) for step in ordered_steps],
                "pass_at_k": [step.get("pass_at_k", 0.0) for step in ordered_steps],
                "avg_tool_calls": [step.get("avg_tool_calls", 0.0) for step in ordered_steps],
            }
        )

    eval_metrics_path = run_dir / "eval_metrics.json"
    if eval_metrics_path.exists():
        st.subheader("Eval Metrics")
        st.json(read_json(eval_metrics_path), expanded=True)

    artifact_tab, step_tab, memory_tab = st.tabs(["Artifacts", "Step Detail", "Experience Memory"])
    with artifact_tab:
        artifacts = sorted(p for p in run_dir.rglob("*") if p.is_file())
        st.dataframe(
            [{"file": relative_posix(path), "updated": format_ts(path)} for path in artifacts],
            use_container_width=True,
            hide_index=True,
        )

    with step_tab:
        if not run["step_dirs"]:
            st.info("This run does not contain step-level practice directories.")
        else:
            step_dir = st.selectbox("Step Directory", run["step_dirs"], format_func=lambda p: p.name)
            files = sorted(p for p in step_dir.iterdir() if p.is_file())
            selected_file = st.selectbox("Artifact File", files, format_func=lambda p: p.name)
            suffix = selected_file.suffix.lower()
            if suffix == ".json":
                st.json(read_json(selected_file), expanded=False)
            elif suffix == ".jsonl":
                rows = load_jsonl(selected_file)
                st.dataframe(rows[:20], use_container_width=True)
                st.caption(f"Showing first {min(len(rows), 20)} rows of {len(rows)} total.")
            else:
                st.code(read_text(selected_file), language="text")

    with memory_tab:
        memory_path = run_dir / "experiences_final.json"
        if memory_path.exists():
            memory = read_json(memory_path)
            st.dataframe(
                [{"id": key, "experience": value} for key, value in memory.items()],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No final experience memory found for this run.")


def config_lab(mode: str, config_name: str) -> None:
    section_header(
        "Config Lab",
        "Trace dependencies before you run",
        "Every practice or eval config fans out into agent settings, models, tools, and datasets. This panel makes those relationships visible so you can reason about the run before spending API calls.",
    )

    config_path = ROOT / config_name
    payload = read_yaml(config_path)
    agent_path = ROOT / payload["agent_config"]
    agent_payload = read_yaml(agent_path)
    eval_payload = None
    if mode == "practice" and payload.get("evaluation_config"):
        eval_payload = read_yaml(ROOT / payload["evaluation_config"])

    left, mid, right = st.columns(3, gap="large")
    with left:
        st.subheader("Primary Config")
        st.code(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), language="yaml")
    with mid:
        st.subheader("Agent Config")
        st.code(yaml.safe_dump(agent_payload, sort_keys=False, allow_unicode=True), language="yaml")
    with right:
        st.subheader("Referenced Eval Config")
        if eval_payload:
            st.code(yaml.safe_dump(eval_payload, sort_keys=False, allow_unicode=True), language="yaml")
        else:
            st.info("No linked eval config for the current selection.")


def data_room(mode: str, config_name: str) -> None:
    section_header(
        "Data Room",
        "Preview the datasets feeding the workflows",
        "The examples are toy JSONL inputs, but this surface is still useful for checking schema, groundtruth presence, and whether a config is pointed at the expected file.",
    )

    payload = read_yaml(ROOT / config_name)
    if mode == "practice":
        dataset_path, rows = dataset_preview(payload["data"]["practice_dataset_path"])
    else:
        dataset_path, rows = dataset_preview(payload["dataset_path"])

    c1, c2 = st.columns([0.72, 0.28], gap="large")
    with c1:
        st.subheader("Dataset Preview")
        st.dataframe(rows, use_container_width=True)
    with c2:
        st.subheader("Dataset Facts")
        metric_card("Source", dataset_path, "forest")
        metric_card("Preview Rows", str(len(rows)), "gold")
        sample_fields = sorted({key for row in rows for key in row.keys()}) if rows else []
        st.caption("Fields: " + (", ".join(sample_fields) if sample_fields else "none"))


def main() -> None:
    st.set_page_config(
        page_title="Training-Free GRPO Command Center",
        layout="wide",
    )
    render_css()

    runs = discovered_runs()
    mode, config_name = sidebar_controls()

    app_header(runs)
    mission_control(runs)

    launch_tab, run_tab, config_tab, data_tab = st.tabs(
        ["Launchpad", "Run Inspector", "Config Lab", "Data Room"]
    )
    with launch_tab:
        launchpad(mode, config_name)
    with run_tab:
        run_inspector(runs)
    with config_tab:
        config_lab(mode, config_name)
    with data_tab:
        data_room(mode, config_name)


if __name__ == "__main__":
    main()
