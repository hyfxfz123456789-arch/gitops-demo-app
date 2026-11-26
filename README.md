# GitOps Demo

这个无第三方依赖的 HTTP 应用用于验证 CI/CD。`/` 显示版本、Git commit 和 Pod 名称；`/api/info` 返回相同信息的 JSON；`/healthz` 用于 Kubernetes 探针。

本地运行：

```bash
APP_VERSION=0.1.0 GIT_COMMIT=local PORT=8080 python3 app.py
curl http://127.0.0.1:8080/api/info
curl http://127.0.0.1:8080/healthz
```

在 node-04 用 Buildah 构建的示例命令：

```bash
HTTPS_PROXY=http://192.168.1.5:10808 HTTP_PROXY=http://192.168.1.5:10808 \
  buildah pull docker.io/library/python:3.13-alpine
buildah bud --build-arg APP_VERSION=0.1.0 --build-arg GIT_COMMIT=local \
  -t localhost/gitops-demo:0.1.0 .
```

当前已在 node-04 构建并推送 `192.168.119.166:8443/gitops-demo/web:0.1.0`。Harbor 中的 `gitops-demo` 项目为私有项目；`gitops-demo` 命名空间使用只读机器人账号对应的 `harbor-pull` Secret 拉取镜像。

在 master 上部署和验证：

```bash
kubectl apply -f k8s/demo.yaml
kubectl rollout status deployment/gitops-demo -n gitops-demo
kubectl get pods,svc,ingress -n gitops-demo -o wide
curl --noproxy '*' --resolve demo.lab:30080:192.168.119.65 \
  http://demo.lab:30080/api/info
```

从浏览器访问 `http://demo.lab:30080/`，需要让浏览器所在主机把 `demo.lab` 解析到可用节点 IP，并对该域名绕过代理。当前镜像的 commit 值为手工验证用的 `local`；接入 Jenkins 后会替换成真实 Git commit。

以后由 Jenkins 把版本与 commit 写入镜像、推送 Harbor，再更新 GitOps 仓库中的镜像标签；Argo CD 根据 GitOps 仓库部署。当前 `k8s/demo.yaml` 是手工验证清单，还没有交给 Argo CD 管理。

Multibranch webhook verification
