aws sts get-caller-identity
node --version            # 20 or later
npm install -g @aws/agentcore
agentcore --version
pip install uv

# the deep-dive samples repo: Days 1 to 3 are built here, one standalone folder per component
mkdir agentcore-deep-dive-samples && cd agentcore-deep-dive-samples && git init
mkdir -p blog
# pitwall-platform and pitwall-samples are created on Day 4 (Module 11)

# the target repo devagent will work on (separate GitHub repo)
gh repo create <you>/shop-api --public --clone
# add: app/main.py (FastAPI), tests/, pyproject.toml with pytest

cp .env.example .env && printf ".env\nagentcore/.env.local\n" >> .gitignore
set -a; source .env; set +a          # load variables into the shell for the setup commands
