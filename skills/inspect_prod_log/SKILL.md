---
name: inspect_prod_log
description: 【环境上下文】提供生产环境日志文件系统结构说明。当涉及“检索日志”、“查看日志”或“排查问题”时，加载此信息以获取日志文件路径和分类知识。
metadata:
  required_skills:
    - import: mcp.shell_mcp
      tools: ["execute_shell"]
---
查询固定文件夹 /prod-log/ 下的日志文件
下面是对应文件夹下面各种日志文件的说明：
- spring.log: **重要** 这个文件是主要的生产文件日志，大多数主要的业务逻辑产生的日志都会记录在这个文件中。同时需要注意的是，这个文件只保留当天的数据，过期的数据会被自动删除。
- ./cloud/spring.log: 这个文件包含了spring-cloud体系下的 gateway、eureka 等组件的日志，如果某些调用在 spring.log 中没有找到相关日志，可能是由于请求在网关阶段被拒绝了，这时候可以在这个文件中查看相关日志。  
- 使用**execute_shell**执行以下命令来查看日志文件：
```bash
# 查看当天的 spring.log 文件
cat /prod-log/spring.log | grep "{keyword}"
# 查看当天的 cloud/spring.log 文件
cat /prod-log/cloud/spring.log | grep "{keyword}"
```
其中 `{keyword}` 是用户提供的关键词，可以是用户 ID、订单 ID、错误码  
**重要提示** ：日志文件通常比较大，在查询时 **必须提供** 关键词来过滤日志内容，避免一次性加载过多数据导致系统性能问题。

具体的关键字应该在具体的业务场景中根据用户的查询需求来确定，例如：
- 如果用户想查询某个用户的相关日志，可以使用用户 ID 作为关键词。
- 如果用户想查询某个订单的相关日志，可以使用订单 ID 作为关键词。
- 如果用户想查询某个错误的相关日志，可以使用错误码作为关键词。
请根据用户的查询需求来确定合适的关键词，并使用上述命令来查看日志文件中的相关内容。
