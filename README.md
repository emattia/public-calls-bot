## Setup 

[Install Slack CLI](https://api.slack.com/automation/quickstart)
```bash
curl -fsSL https://downloads.slack-edge.com/slack-cli/install.sh | bash
```

Authenticate the `#public-calls-for-alignment` channel
```bash
slack login
```

## Virtual environment
```bash
mamba create -n public-calls-bot python=3.12 pip
pip install -r requirements.txt
```