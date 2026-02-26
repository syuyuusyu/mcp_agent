v="v2.0"
#ip="docker.io/syuyuusyu"
ip="swr.cn-north-1.myhuaweicloud.com/bqm"
name="mcp-agent"
docker buildx build --platform linux/amd64 --load -t $ip/$name:$v . &&
docker push $ip/$name:$v &&
echo $ip/$name:$v