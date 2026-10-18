# btc-data-collector

比特币行情与情绪数据的 24 小时采集器，跑在 GitHub Actions 上，每 10 分钟一次。
不需要服务器、不需要 API key、公开仓库免费无限分钟。

采集什么、存在哪里，见 `collect.py` 顶部注释。数据在 `data/` 目录，CSV 格式，可直接用 pandas 读。

## 启用

1. 把这个目录推成一个 **公开** GitHub 仓库（私有仓库每月只有 2000 分钟免费额度，10 分钟一次会用超）。
2. 仓库 Settings → Actions → General → Workflow permissions 选 "Read and write permissions"。
3. Actions 页签里手动运行一次 `collect-btc-data`，确认 `data/` 出现文件。

## 注意

- GitHub 对连续 60 天没有人类提交的仓库会自动暂停定时任务。每两个月随便改一下 README 提交一次即可，或者让每日任务顺手做。
- 分钟线数据一年约 50 万行、25 MB，三年内不用担心仓库体积。
