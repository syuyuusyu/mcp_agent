---
name: common-question
description: 【SOP标准流程】当前流程用来维护表 `common_question` 中的数据，当用户给出一些问题和答案时，使用此工具来更新数据库中的相关记录。 当用户输入包含 "维护常见问题" 时，必须优先使用此工具。此工具内部已封装了完整的数据库查询和更新逻辑，不要手动调用 `execute_sql` 或 `list_tables` 去重新探索。
metadata:
  required_skills:
    - import: mcp.mysql_mcp
      tools: ["exec_sql_batch", "execute_sql"]
---
**注意：此任务的主要目的是维护数据，而不是维护问题本身。**
当前流程处理用户反馈的常见问题数据维护，主要针对表 `common_question` 中的数据进行清理和更新。此流程会查询数据库中与用户反馈相关的常见问题信息，并根据用户选择删除或更新相关数据。
表结构 如下：

```sql  
CREATE TABLE `common_question` (
  `id` INT(8) AUTO_INCREMENT PRIMARY KEY,
  `hp_id` varchar(20),
  `topic` varchar(100),
  `question` TEXT,
  `answer` TEXT
)
```

**表中的 tipic 是一个固定枚举值，目前包含以下几种类型：**
  - 报告查询
  - 其他
  - 门诊缴费
  - 挂号问题
  - 住院
  - 登录注册
  - 绑卡
  - 预约挂号

**步骤 1：验证输入**
- 用户的输入需要包含一个问题和一个答案，以及对应的问题类型（topic）如果没有提供 topic，则帮助用户选择一个合适的 topic。
- 如果用户没有提供问题或答案，请提示用户提供完整的信息。
- 如果用户提供的 topic 不完全对应上述枚举值，则自动选择一个意思接近的枚举值，如果无法确定，请提示用户选择一个有效的 topic。
- hp_id 必须由用户提供，模型不需要关心 hp_id 的生成逻辑，只需要确保用户提供了一个 hp_id。

**步骤 2：查询数据**
- 使用数据库工具执行以下 SQL 查询是否已经存在相同 hp_id 和 topic 的记录：
  ```sql
  select * from common_question where hp_id = '{hp_id}' and topic = '{topic}';
  ```
- 观察查询结果：
  - **分析是否已经有相同的问题**: 没有找到任何相关记录，则可以插入新的问题和答案。
  - **如果找到相同的问题**: 先记住当前问题的`id`,如果需要更新则通过`id`，操作，或者提示用户该问题已经存在。

**步骤 3：执行更新或插入**
- 如果用户选择插入新的记录，执行以下 SQL，
  ```sql
  insert into common_question (hp_id, topic, question, answer) values ('{hp_id}', '{topic}', '{question}', '{answer}');
  ```
- 如果用户选择更新现有记录，执行以下 SQL：
  ```sql
  update common_question set question = '{question}', answer = '{answer}' where id = '{id}';
  ```
- 执行完成后反馈结果。

**重要规则**： 
  - topic 必须是上述枚举值之一，如果用户输入的 topic 不完全匹配上述枚举值，模型需要自动选择一个意思接近的枚举值，如果无法确定，请提示用户选择一个有效的 topic。
  - 需要比对用户给用户给的问题和现有数据的问题是否相似，如果相似度较高（比如超过80%），则提示用户该问题已经存在，并询问用户是否需要更新现有记录。