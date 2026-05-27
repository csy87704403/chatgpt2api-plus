# Linux VPS 部署

推荐使用 Docker Compose 部署。数据会保存在当前目录的 `data/`，配置保存在 `config.json`，这两个都不会提交到 Git。

默认部署方式是从 GitHub Container Registry 拉取已经构建好的镜像，不在 VPS 上现场构建。这样安装更快，也更少遇到 Docker Hub 下载慢的问题。

## 首次安装

```bash
git clone https://github.com/YOUR_NAME/YOUR_REPO.git
cd YOUR_REPO
bash scripts/install-linux.sh
```

安装脚本会自动：

- 检查并安装 Docker
- 从 `config.example.json` 生成 `config.json`
- 生成 `.env` 和随机登录密钥
- 自动推断 `CHATGPT2API_IMAGE`
- 拉取 GHCR 镜像并执行 `docker compose up -d`

首次推送代码到 GitHub 后，仓库里的 GitHub Actions 会自动构建镜像。等 Actions 跑完后，再到 VPS 执行安装脚本。

启动后访问：

```text
http://你的服务器IP:3000
```

登录密钥会在安装脚本最后输出，也可以查看：

```bash
cat .env
```

## 更新

```bash
cd YOUR_REPO
bash scripts/update-linux.sh
```

## 常用命令

```bash
docker compose logs -f
docker compose restart
docker compose down
```

如果你确实想在当前机器上现场构建镜像，可以执行：

```bash
docker compose -f docker-compose.local.yml up -d --build
```

## 代理

如果 VPS 不能直连 `chatgpt.com`，需要在 `config.json` 里设置：

```json
"proxy": "http://你的代理地址:端口"
```

修改后重启：

```bash
docker compose restart
```

## 重要提醒

不要提交这些文件：

- `config.json`
- `.env`
- `data/`

里面可能包含登录密钥、账号 token、图片记录和运行日志。
