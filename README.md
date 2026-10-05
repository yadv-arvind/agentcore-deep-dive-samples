# agentcore-deep-dive-samples

Sample code for a multi-day deep dive into building agents with the AWS AgentCore CLI (`@aws/agentcore`). Days 1 to 3 are built in this repository, one standalone folder per component.

## Repository structure

| Path | What's inside |
|:-----|:--------------|
| [`setup.sh`](./setup.sh) | Checks your tools, installs the AgentCore CLI and `uv`, creates the `shop-api` target repo, and prepares `.env` |
| `blog/` | Created by `setup.sh` for the write-ups that accompany the samples |
| [`LICENSE`](./LICENSE) | MIT license |

Each component folder is added as its day is built. `pitwall-platform` and `pitwall-samples` are created on Day 4 (Module 11) and live outside this repository.

## Prerequisites

| Requirement | Minimum version | Install |
|:------------|:----------------|:--------|
| AWS CLI | any current version | [Install the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| Node.js | 20 | [nodejs.org](https://nodejs.org/) |
| Python and `pip` | any current 3.x | [python.org](https://www.python.org/downloads/) |
| GitHub CLI (`gh`) | any current version | [cli.github.com](https://cli.github.com/) |

Verify that your AWS credentials work:

```bash
aws sts get-caller-identity
```

## Quick start

Run the setup script from the repository root. Pass your GitHub username so it can create the `shop-api` repo:

```bash
./setup.sh <your-github-username>
```

The script runs these steps in order and stops on the first error:

1. Verifies AWS credentials and Node 20 or later.
2. Installs the AgentCore CLI globally with `npm install -g @aws/agentcore` and prints `agentcore --version`.
3. Installs `uv` with `pip install uv` if it is missing.
4. Runs `git init` if needed and creates `blog/`.
5. Creates a public `<your-github-username>/shop-api` repo with `gh repo create` and clones it to `../shop-api`.
6. Copies `.env.example` to `.env` if `.env` is missing, and adds `.env` and `agentcore/.env.local` to `.gitignore`.

You can re-run the script safely. It skips the clone if `../shop-api` exists and skips `.env` creation if the file exists. Without a GitHub username (argument or `GH_USER`), it skips the `shop-api` step.

`shop-api` is the repo the `devagent` component works on. The script does not populate it, so add `app/main.py` (FastAPI), `tests/`, and a `pyproject.toml` with pytest yourself.

To load `.env` into your own shell, run this. The script's own `source` doesn't carry over to your terminal.

```bash
set -a; source .env; set +a
```

## Configuration

| Variable | Default | Description |
|:---------|:--------|:------------|
| `GH_USER` | none | GitHub user for `shop-api`, used when no argument is passed |
| `SHOP_API_DIR` | `../shop-api` | Where `shop-api` is cloned, or where an existing clone is expected |

> [!NOTE]
> `setup.sh` copies `.env.example` when it exists, but this repository doesn't contain one yet. Until one is added, the script prints a message and skips creating `.env`.

## Clean up

Setup installs the AgentCore CLI globally and creates a public GitHub repo. Remove them when you finish:

```bash
npm uninstall -g @aws/agentcore
gh repo delete <your-github-username>/shop-api
rm -rf ../shop-api
```

This removes the CLI and the `shop-api` repo, both on GitHub and locally. `gh repo delete` asks for confirmation and needs the `delete_repo` scope. `uv` stays installed.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
