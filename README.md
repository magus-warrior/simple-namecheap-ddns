# simple-namecheap-ddns
I simple interface for setting up DDNS with namecheap

## Environment

Both the agent and the webapp read the agent log database path from
`AGENT_DB_PATH`. If it is not set, they fall back to
`${DDNS_WORKDIR}/.ddns/agent.db`.
