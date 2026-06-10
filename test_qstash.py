from qstash.client import QStash

client = QStash(
    "eyJVc2VySUQiOiJlOGVlNTVkYS1jZmQ4LTQ0YzctODQ1Yi0wMmU3NTI0NzU4MzEiLCJQYXNzd29yZCI6IjdjNDM0MGUzYzEwODQ1ODJiMDUwOWIyOTkxNDc4YzkwIn0=",
    base_url="https://qstash-eu-central-1.upstash.io",
)

response = client.message.publish_json(
    url="https://github-ai-pr-reviewer-orchestrator.onrender.com/test",
    body={"hello": "world"},
)

print(response)