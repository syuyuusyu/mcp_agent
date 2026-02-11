from langgraph.checkpoint.postgres import PostgresSaver

from app.utils import logger,load_config_yaml,random_string,repo_root

from app.dependencies import Container,set_container

container = Container()
set_container(container)

db_client = container.db_client()

topic_id = "4"

user_id_list = db_client.query(f"select user_id from ai_topic where id = '{topic_id}'")
user_id = user_id_list[0]['user_id'] if user_id_list else "unknown_user"
topic_count_list = db_client.query(f"select count(1) count from ai_topic where user_id = '{user_id}'")
toppic_count = topic_count_list[0]['count'] if topic_count_list else 0

print(toppic_count)

