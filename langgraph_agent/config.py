"""Load workshop config values from agent_workshop/config.yml."""
import os
import yaml

_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yml")
with open(_config_path) as _f:
    CONFIG = yaml.safe_load(_f)

UC_CATALOG = CONFIG["uc_catalog"]
UC_SCHEMA = CONFIG["uc_schema"]
TABLE_POSTFIX = CONFIG.get("table_postfix", "")
GENIE_SPACE_ID = CONFIG["genie_agent_id"]
VS_ENDPOINT_NAME = CONFIG["vs_endpoint_name"]
VS_INDEX_NAME = f"{UC_CATALOG}.{UC_SCHEMA}.{CONFIG['vs_index_name']}{TABLE_POSTFIX}"
EMBEDDING_MODEL = CONFIG["embedding_model"]
LLM_ENDPOINT = "databricks-gpt-5-5"
