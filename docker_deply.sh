v="v1.0.0"
ip="docker.io"
name="syuyuusyu/mcp-agent"
docker buildx build --platform linux/amd64 --load -t $ip/$name:$v . &&
docker push $ip/$name:$v &&
echo $ip/$name:$v