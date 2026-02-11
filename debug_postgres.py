import psycopg
import sys
import yaml
from langgraph.checkpoint.postgres import PostgresSaver
from app.utils import load_config_yaml


config = load_config_yaml('config.yaml')
pg = config.get("postgres", {})

# Construct connection string
base_conn_string = f"postgresql://{pg.get('user')}:{pg.get('password')}@{pg.get('host')}/{pg.get('database')}"

print(f"Base Connection String: {base_conn_string.replace(pg.get('password'), '******')}")

def test_connection(url, name):
    print(f"\n--- Testing mode: {name} ---")
    try:
        # 1. Raw psycopg test
        print(f"Attempting raw connection...")
        with psycopg.connect(url) as conn:
            print(f"  [Success] Raw connection established.")
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                v = cur.fetchone()
                print(f"  [Success] Select version: {v}")
        
        # 2. Saver test
        print(f"Attempting Saver.setup()...")
        with PostgresSaver.from_conn_string(url) as saver:
            saver.setup()
            print(f"  [Success] Saver setup complete.")
            
    except Exception as e:
        print(f"  [FAILED] Error: {e}")

# Test 1: Default
test_connection(base_conn_string, "Default")

# Test 2: SSL Require
test_connection(base_conn_string + "?sslmode=require", "SSL Mode = Require")

# Test 3: SSL Disable (if server doesn't support it)
test_connection(base_conn_string + "?sslmode=disable", "SSL Mode = Disable")
