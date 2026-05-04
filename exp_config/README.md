## Setup Instructions

You can either follow the official setup guide from the MassGen README, or quickly set up the environment using the commands below.

### 1. Create and Activate Virtual Environment

```bash
(inside MassGen)
pip install uv
uv venv
source .venv/bin/activate
uv pip install massgen
```

To set your API key, use the command and select OpenRouter in the “Select Providers” step. This is only required for Kimi and Grok.

For Claude Code (subscription-based), simply log in to Claude Code within VS Code.

During setup, just press “Next” for the Docker step since we will pull the Docker image manually, and continue pressing “Next” for all remaining options.

```bash
uv run massgen --setup
```
---

### 2. Pull Required Docker Image

Download the runtime container:

```bash
docker pull ghcr.io/massgen/mcp-runtime-sudo:v0.1.79
```

---

### 3. Run the Experiment

Navigate to the `MassGen/` directory and copy paste you prompt into `prompt.txt` select the corresponding yaml and execute:

```bash
bash exp_config/run.sh exp_config/claude.yaml exp_config/prompt.txt (for calude)

bash exp_config/run.sh exp_config/Grok.yaml exp_config/prompt.txt (for Grok)

bash exp_config/run.sh exp_config/kimi.yaml exp_config/prompt.txt (for Kimi)
```

---

### 4. Configuration Notes

Before running:

- Update the configuration file to match your experiment setup  
- Copy your prompt into `prompt.txt`


### 5. Running
After running the task, you will see logs like:

LOG_DIR: XXX/.massgen/massgen_logs/log_20260504_091232_086385

STATUS: XXX/MassGen/.massgen/massgen_logs/log_20260504_091232_086385/turn_1/attempt_1/status.json

QUESTION: First few words of your prompt

**When the run finishes successfully, the terminal will display something like:**

WINNER: agent_a

ANSWER_FILE: .massgen/massgen_logs/log_20260504_091232_086385/turn_1/attempt_1/final/agent_a/answer.txt

DURATION: 459.7s

This indicates a successful run.

When uploading results, please compress (zip) everything inside the LOG_DIR directory not FINAL_DIR!