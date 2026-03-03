---
name: fix_user_data_issue
description: 【SOP标准流程】通过手机号梳理并调整用户数据，当用户输入包含手机号和 "处理｜查看用户数据"、"处理｜查看用户"、"查看用户信息" 时，必须优先使用此工具。此工具内部已封装了完整的数据库查询和删除逻辑，不要手动调用 `execute_sql` 或 `list_tables` 去重新探索。
metadata:
  required_skills:
    - import: mcp.mysql_mcp
      tools: ["list_databases", "list_tables", "execute_sql"]
---
当前流程处理用户不能正常登录时的用户数据清理，主要针对手机号对应的union_id重复问题。此流程会查询数据库中与用户手机号相关的所有账号信息，并根据用户选择删除多余的账号数据。

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
  - **Case A (记录数 = 0)**: 没有找到任何相关数据，告知用户没有发现相关账号信息，建议用户检查输入的电话号码是否正确。并结束当前流程。
  - **Case A (记录数 = 1)**: 没有发现重复数据，跳转到 **union_id变动子流程**
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

**union_id变动子流程**  
用户无法正常登录，除了上述的重复数据问题外，还有可能是用户的 `union_id` 发生了变动。此时需要执行以下步骤：
当前子流程需要查询生产日志，有关查询日志的细节请参考 skills inspect_prod_log 中的相关说明。  

**步骤 1：查询用户是否由于无法登录而进行了注册**
- 使用keyword `{phone}注册返回手机号已注册` 来查询日志文件，查看是否有用户在近期进行了注册操作。
- 如果上述查询有结果，则应该返回入下信息 `{phone}注册返回手机号已注册,unionId:{unionId}` 此时进行下一步操作
- 如果上述查询没有结果，则当前的情况程序无法处理，应该告知用户当前的情况程序无法处理，并结束当前流程。  

**步骤 2：查询用户在注册前是否使用对应的unionId登录过**
- 使用keyword `unionId:{unionId},登录返回用户未注册` 来查询日志文件，查看是否有用户在近期进行了登录操作。
- 如果上述查询有结果，则应该返回入下信息 `unionId:{unionId},登录返回用户未注册` 此时进行下一步操作
- 如果上述查询没有结果，则当前的情况程序无法处理，应该告知用户当前的情况程序无法处理，并结束当前流程。  

**步骤 3：修改用户表的union_id**
- 此时已经可以判定用户的union_id发生了变动，需要执行以下SQL来修改用户表中的union_id：此时的 `{unionId}` 是上面日志查询得到的值，`{phone}` 是用户的电话号码。不用理会base_user表中原来的union_id是什么值，直接执行更新操作即可。
```sql
update base_user set union_id = '{unionId}' where phone = '{phone}' and type='0';
```
- 执行完成后反馈结果。
**注意** 在使用keyword 查询日志时，空格或者逗号等特殊字符可能会对查询结果产生影响，请根据实际情况调整查询关键词的格式以确保能够正确匹配日志内容。
