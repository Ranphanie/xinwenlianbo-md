# 新闻联播 Markdown 自动整理

每天从央视网《新闻联播》栏目页抓取当天「本期节目主要内容」，生成 Markdown 文稿，并提供给 iPhone 快捷指令保存到 Obsidian。

## 产物地址

快捷指令只需要读取这个 JSON：

```text
https://raw.githubusercontent.com/Ranphanie/xinwenlianbo-md/main/generated/latest.json
```

`latest.json` 会包含当天 Markdown 下载地址、Obsidian vault 名称、目标笔记路径和可打开的 Obsidian URI。

## 保存规则

当前配置：

- Obsidian vault：`新闻联播`
- 笔记路径：`YYYY/YYYY-MM-DD 新闻联播`

例如：

```text
2026/2026-06-08 新闻联播
2027/2027-01-01 新闻联播
```

如果 Obsidian iOS 无法自动创建年份文件夹，可以把 GitHub Actions 里的生成命令改成：

```bash
python scripts/generate_xwlb.py --out-dir generated --repo Ranphanie/xinwenlianbo-md --branch main --obsidian-vault 新闻联播 --no-year-folder
```

这样会保存为：

```text
2026-06-08 新闻联播
```

## GitHub Actions

`.github/workflows/generate.yml` 会在北京时间晚间多个时间点自动运行：

- 20:45
- 21:15
- 21:45
- 22:15

这些时间都显式使用 `Asia/Shanghai` 时区，并避开整点高峰。脚本默认以「北京时间当天」为目标；如果央视栏目页还没有当天节目，或链接日期与目标日期不一致，脚本只输出 `skipped` 状态，不更新 `latest.json`，避免手机打开旧文稿。

流程如下：

1. 安装 Python 依赖。
2. 运行测试。
3. 抓取北京时间当天《新闻联播》。
4. 只有当天节目已发布且日期匹配时，生成 `generated/YYYY/YYYY-MM-DD 新闻联播.md` 和 `generated/latest.json`。
5. 如果产物有变化，自动提交回仓库。

也可以通过两种方式手动运行：

- 在 GitHub 网页进入 **Actions → Generate Xinwenlianbo Markdown → Run workflow**。
- 用 iPhone 快捷指令调用 GitHub `workflow_dispatch` API 触发。

## iPhone 快捷指令设置

在 iPhone 上打开「快捷指令」，新建一个快捷指令，例如命名为「保存新闻联播」。

基础读取版快捷指令动作按下面顺序添加：

1. **获取 URL 内容**
   - URL 填：
     ```text
     https://raw.githubusercontent.com/Ranphanie/xinwenlianbo-md/main/generated/latest.json
     ```
2. **从输入中获取字典**
3. **从字典获取值**
   - 键：`markdown_url`
4. **获取 URL 内容**
   - URL 使用上一步得到的 `markdown_url`
5. **拷贝到剪贴板**
   - 内容使用上一步下载到的 Markdown 正文
6. **从字典获取值**
   - 回到第 2 步得到的字典
   - 键路径：`obsidian.uri`
7. **打开 URL**
   - URL 使用上一步得到的 Obsidian URI

完成后，在「自动化」里创建个人自动化：

- 触发条件：每天 21:40 左右
- 动作：运行「保存新闻联播」
- 关闭「运行前询问」

如果 iOS 提示需要确认打开 Obsidian，属于系统限制；确认一次后通常会更顺。

如果配置了「手机触发 GitHub Actions」版本，快捷指令应先触发 workflow，再轮询 `latest.json`。只有当 `latest.json` 的 `date` 等于当天北京时间日期时，才继续下载 Markdown 并打开 Obsidian；否则停止并提示当天文稿尚未生成。

## 本地开发

```bash
py -m pip install -r requirements.txt
py -m pytest
py scripts/generate_xwlb.py --date 2026-06-08 --out-dir generated --repo Ranphanie/xinwenlianbo-md --branch main --obsidian-vault 新闻联播
```
