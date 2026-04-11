---
name: get-system-api
description: 【环境上下文】本skills用来描述如何获取系统接口的Swagger标准文档
metadata:
  required_skills:
    - import: mcp.shell_mcp
      tools: ["execute_command"]
---

***系统背景***
当前系统是一个使用spring-cloud构建的微服务架构，所有的接口都通过Swagger进行文档化和管理。系统中包含多个微服务，每个微服务都有自己的Swagger文档，用户可以通过访问这些文档来了解各个接口的功能、参数和返回值。

***系统模块***
  - 基础 base-service
  - 通用 common-service
  - HIS his-service
  - 网易云信 netease-service
  - 第三方接口 third-service
  - 在线诊疗 om-service

***获取Swagger文档的接口***  
  https://www.51bqm.com:7022/{模块名称}/v3/api-docs?access_token={access_token}
  其中，{模块名称}需要替换为具体的模块名称，例如：base-service、common-service、his-service、netease-service、third-service、om-service等。{access_token}需要替换为有效的访问令牌。
  access_token 应该存在于聊天上下文中，模型可以直接从上下文中获取并使用，无需用户每次都提供。
  使用 curl 通过上述url可以获取到对应模块的Swagger文档，文档内容是一个JSON格式的数据，包含了该模块所有接口的详细信息。

***使用场景***  
  当前skills 作为一个辅助工具，当用户需求中的某个操作需要调用系统接口时，模型可以使用此skills来获取对应模块的Swagger文档，从而了解接口的具体信息，以便正确地调用接口完成用户的需求。
  ***重要提提示:*** 模型在获取接口文档后就可以直接调用对应的接口，如果是查询类的接口，模型可以根据具体的用户需求来直接调用，如果是操作类的接口，则需要先询问用户是否需要调用接口来完成操作，**只有在用户确认后才进行接口调用**。 这样可以避免模型在不确定的情况下随意调用接口，确保用户的需求得到正确的处理。接口的类型(查询类还是操作类)可以通过分析接口的功能描述或者接口的命名来判断，如果无法确定接口的类型，可以先询问用户接口的用途来进行判断。
  如果调用接口的参数模型不清楚，可以先通过获取Swagger文档来了解接口的参数要求，然后再向用户确认需要调用哪个接口以及需要提供哪些参数，最后再进行接口调用。
  所有接口都使用 curl 来调用，模型需要根据Swagger文档中的接口信息来构造正确的curl命令，包括URL、请求方法、请求头和请求体等。模型需要确保curl命令的正确性，以便成功调用接口并获取正确的响应结果。
  不是所有的接口文档都会有明确的调用信息，会有类似请求体为 @RequestBody body:Map<String,String?> 这样的接口， 如果模型不能推断接口的用途和调用参数，者可以忽略这些接口。 **不要在不清楚接口用途和调用参数的情况下随意调用接口**，以免造成不必要的错误和混乱。

***特别说明***
  存在一个特殊接口
  ```
  https://www.51bqm.com:7022/user/dev/userInfo
  method: POST
  head:
  {
    "access_token": "{access_token}"
  }
  body:
  {
    "userId": "{userId}"
  }
  ```
  由于access_token 保存的是当前用户的信息，而这个接口可以用来换取对应{userId}的access_token. 由于特定的接口需要特定的用户进行操作， 如果出现这样的场景，模型需要先通过这个接口来获取对应用户的access_token，然后再使用这个access_token来调用其他接口。 例如，如果需要查询某个用户的订单信息，而当前的access_token不具有查询该用户订单信息的权限，那么模型可以先通过上述接口来获取该用户的access_token，然后再使用这个新的access_token来查询订单信息。 这样可以确保模型在调用接口时具有正确的权限，从而成功完成用户的需求。

