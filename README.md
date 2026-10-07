# agentcore-deep-dive-samples

Sample code for a deep dive into building agents with [Strands Agents](https://strandsagents.com/) and Amazon Bedrock AgentCore, one standalone folder per component.

## Repository structure

| Path | What's inside |
|:-----|:--------------|
| [`00-strands-spec-coder/`](./00-strands-spec-coder/) | Planner, coder and reviewer agents that implement a change in a local repo, with an independent check of the result |
| [`settings.py`](./settings.py) | Loads `.env` and `resources.yaml`. Every sample imports it with `from settings import settings`. |
| [`resources.yaml`](./resources.yaml) | Non-secret settings: the Bedrock model ID |
| [`.env.example`](./.env.example) | Template for the environment variables and secrets. Copy it to `.env`. |
| [`requirements.txt`](./requirements.txt) | Pinned Python dependencies |
| [`setup.sh`](./setup.sh) | The first-time setup commands, in order |
| [`LICENSE`](./LICENSE) | MIT license |

## Finding things

- **Start here** → [`00-strands-spec-coder/`](./00-strands-spec-coder/), the local multi-agent coder
- **By tool** → Strands Agents: `00-strands-spec-coder/`

More component folders are added as they are built.

## Prerequisites

| Requirement | Needed for | Install |
|:------------|:-----------|:--------|
| Python 3.12 and [uv](https://astral.sh/uv) | `00-strands-spec-coder/` | `brew install uv` |
| AWS CLI with credentials | Every sample | [Install the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| Node.js 20 or later and the `@aws/agentcore` CLI | Later components, per `setup.sh` | `npm install -g @aws/agentcore` |
| GitHub CLI (`gh`) | Creating the target repo in `setup.sh` | `brew install gh` |

Verify your AWS credentials:

```bash
aws sts get-caller-identity
```

You also need access to Amazon Nova Pro on Amazon Bedrock in a US region. See [Bedrock model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html).

## Quick start

Run these from the repository root.

```bash
# 1. Create the environment and install the pinned dependencies
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Configure: edit .env and set AWS_REGION. Uncomment AWS_PROFILE only if you use a named profile.
cp .env.example .env
```

Then follow [`00-strands-spec-coder/README.md`](./00-strands-spec-coder/README.md) to run the sample against a target repo.

[`setup.sh`](./setup.sh) lists the full setup commands from the start. Run them one at a time instead of executing the file:

- Replace `<you>` in the `gh repo create` line with your GitHub username.
- The `mkdir agentcore-deep-dive-samples` line creates this repo from scratch. Skip it, because you already have the repo.

## Results snapshot

A run of `00-strands-spec-coder` against a small FastAPI repo, `shop-api`, with the request "Add a DELETE /items/{item_id} endpoint". The independent check at the end of the run reported:

```text
== Independent check (not the agents' report) ==
Changed files:
  app/main.py: +8 -0
  tests/test_items.py: +16 -0
Tests: 4 before, 6 after. pytest: 6 passed, 1 warning in 0.11s
No problems found.
```

The sample's README has the [full output](./00-strands-spec-coder/README.md#sample-run) of this run.

## Configuration

Secrets go in `.env`, which git ignores. Everything else goes in `resources.yaml`.

| Setting | File | Description |
|:--------|:-----|:------------|
| `AWS_REGION` | `.env` | Required. Use a US region for the Nova Pro model ID. |
| `AWS_PROFILE` | `.env` | Optional. Commented out in `.env.example`. Set it only if you use a named profile. |
| `model_id` | `resources.yaml` | Bedrock model ID, `us.amazon.nova-pro-v1:0` |

## Clean up

The samples in this repo deploy nothing. The setup steps create three things you may want to remove:

```bash
# The virtual environment and your local settings
rm -rf .venv .env

# The AgentCore CLI, if you installed it
npm uninstall -g @aws/agentcore

# The target repo on GitHub and its local clone (this deletes the GitHub repo permanently)
gh repo delete <you>/shop-api
rm -rf ../shop-api
```

`gh repo delete` asks for confirmation and needs the `delete_repo` scope. `uv` stays installed.

## Additional resources

- [Strands Agents](https://strandsagents.com/)
- [Strands Agents SDK for Python](https://github.com/strands-agents/sdk-python)
- [Strands Agents tools](https://github.com/strands-agents/tools)
- [Bedrock model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
