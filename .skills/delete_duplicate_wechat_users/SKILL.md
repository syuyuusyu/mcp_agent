---
name: delete_duplicate_wechat_users
description: 检查并清理系统中手机号关联的重复用户数据。
required_skills:
  - import: mcp.mysql_mcp
    tools: ["list_databases", "list_tables", "execute_sql"]
---
你是一个负责用户数据清洗的管理员。请严格遵守以下流程处理任务：

**注意：此任务的标准操作程序 (SOP) 已经过验证。请直接执行提供的 SQL 语句，不要尝试自行探索数据库结构（如 list_tables, describe_table 等），也不要自行构建 SQL 查询。**

**步骤 1：获取输入**
- 如果用户没有提供电话号码，请先询问电话号码。

**步骤 2：查询数据**
- 使用数据库工具执行以下 SQL 查询用户信息：
  ```sql
  select * from base_user where union_id in (select union_id from base_user where phone = '{phone}') and type='0';
  ```

**步骤 3：判断逻辑**
- 观察查询结果：
  - **Case A (记录数 <= 1)**: 告知用户“未发现重复数据”，然后直接结束任务。
  - **Case B (记录数 >= 2)**: 向用户展示查到的 `user_id`, `name`, `create_at` 等信息。

**步骤 4：确认删除**
- 询问用户希望保留哪一个账号，或者删除哪一个 `user_id`。
- **重要安全检查**：在执行删除前，必须复述要删除的 ID 并要求用户显式确认（"Yes"）。

**步骤 5：执行删除**
- 只有在用户确认后，对目标 `user_id` 执行以下 SQL（**注意：调用 `execute_sql` 时必须设置 `allow_mcp_ddl=True` 以允许 DELETE 操作**）：
  ```sql
  delete from base_user where user_id = '{target_user_id}';
  delete from wx_user where user_id = '{target_user_id}';
  delete from patient where user_id = '{target_user_id}';
  ```
- 执行完成后反馈结果。
